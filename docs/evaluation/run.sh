#!/usr/bin/env bash
# =============================================================================
# git-llm black-box evaluation driver
# =============================================================================
# Runs all 7 scenarios from docs/evaluation/scenarios.md against the pi.dev
# sessions for THIS repo. Produces eval-run/<timestamp>/ with all CLI outputs.
#
# No source-code introspection. Only `gitllm` CLI + SQLite queries + standard
# unix tools. Requires: venv activated OR .venv at repo root.
# =============================================================================

set -uo pipefail   # NOTE: not -e - we WANT failures to record, not abort.

# -----------------------------------------------------------------------------
# 0. Resolve repo root + activate venv
# -----------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "${REPO_ROOT}"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Load API keys (ANTHROPIC_API_KEY, etc.) — .env first, scripts/.env as fallback
if [[ -f .env ]]; then
  set -a; source .env; set +a
elif [[ -f scripts/.env ]]; then
  set -a; source scripts/.env; set +a
fi

# Verify gitllm is available
if ! command -v gitllm &>/dev/null; then
  echo "[FATAL] 'gitllm' not found on PATH. Activate your venv or pip install -e .[dev]"
  exit 1
fi

# -----------------------------------------------------------------------------
# 0b. Setup run directory + DB path
# -----------------------------------------------------------------------------
TS="$(date +%Y%m%dT%H%M%S)"
RUN_DIR="${REPO_ROOT}/eval-run/${TS}"
mkdir -p "${RUN_DIR}/zettel"
ln -sfn "${TS}" eval-run/latest

GITLLM_DB="${RUN_DIR}/db.sqlite"
SESS_DIR="${HOME}/.pi/agent/sessions/--Users-michal-PycharmProjects-git-llm--"

log() { echo -e "\n\033[1;34m[eval]\033[0m $*"; }

log "Eval run directory: ${RUN_DIR}"
log "DB: ${GITLLM_DB}"
log "Git SHA: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" > "${RUN_DIR}/_git_sha.txt"

# Helper: query the eval DB and return JSON (replaces missing --json flag)
qdb() {
  python3 -c "
import sqlite3, json, sys
conn = sqlite3.connect('${GITLLM_DB}')
conn.row_factory = sqlite3.Row
try:
    rows = conn.execute(sys.argv[1]).fetchall()
    print(json.dumps([dict(r) for r in rows], indent=2))
except Exception as e:
    print(json.dumps({'error': str(e)}))
conn.close()
" "$1"
}

# =============================================================================
# Scenario 1 - Ingestion
# =============================================================================
log "Scenario 1: Ingestion correctness"

gitllm init --db "${GITLLM_DB}" \
  > "${RUN_DIR}/01-init.log" 2>&1

# Bulk import all sessions for this repo
gitllm import-pi --all --repo git-llm --db "${GITLLM_DB}" \
  > "${RUN_DIR}/01-ingest.log" 2>&1 || true

# Re-import to test idempotency
gitllm import-pi --all --repo git-llm --db "${GITLLM_DB}" \
  > "${RUN_DIR}/01-reingest.log" 2>&1 || true

# Verify: find session-2 chat_id by searching for distinctive P5 text
# (pi-session-export was mentioned in prompt 5)
gitllm search --text 'pi-session-export' --db "${GITLLM_DB}" --limit 1 \
  > "${RUN_DIR}/01-verify-pi.txt" 2>&1 || true

# Resolve chat_id via direct SQLite query on the session with most user turns
CHAT_ID="$(qdb "
  SELECT c.id
  FROM chats c
  JOIN turns t ON t.chat_id = c.id
  WHERE t.role = 'user'
  GROUP BY c.id
  ORDER BY COUNT(*) DESC
  LIMIT 1
" 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["id"] if d else "")' 2>/dev/null || echo '')"

echo "${CHAT_ID}" > "${RUN_DIR}/_chat_id.txt"
log "Session-2 (most user turns) chat_id resolved to: ${CHAT_ID:-<unresolved>}"

# Additional verification queries
qdb "SELECT id, title, session_id FROM chats" > "${RUN_DIR}/01-chats.json"
qdb "
  SELECT t.role, COUNT(*) AS n
  FROM turns t
  WHERE t.chat_id = ${CHAT_ID:-0}
  GROUP BY t.role
" > "${RUN_DIR}/01-turn-counts.json"

log "  Ingestion verification saved to 01-chats.json + 01-turn-counts.json"

# =============================================================================
# Scenario 2 - Labeling
# =============================================================================
log "Scenario 2: Labeling (stub + LLM)"

if [[ -n "${CHAT_ID}" ]]; then
  # Stub labeler (offline, no API key)
  gitllm label "${CHAT_ID}" --model stub --db "${GITLLM_DB}" \
    > "${RUN_DIR}/02-stub-labels.log" 2>&1

  # Export labeled turns as JSONL for human review
  gitllm export "${CHAT_ID}" "${RUN_DIR}/02-stub-labels.jsonl" --db "${GITLLM_DB}" \
    > /dev/null 2>&1

  # Also dump labels to JSON for structured comparison
  qdb "
    SELECT t.idx, t.role, t.parent_id, l.name AS label, l.master_class, l.confidence
    FROM turns t
    JOIN labels l ON l.turn_id = t.id
    WHERE t.chat_id = ${CHAT_ID}
    ORDER BY t.idx
  " > "${RUN_DIR}/02-labels.json"

  # LLM labeler (requires API key + model)
  # Supports: ANTHROPIC_API_KEY or OPENAI_API_KEY. Override model via GITLLM_LABEL_MODEL.
  LLM_MODEL="${GITLLM_LABEL_MODEL:-claude-sonnet-4-5}"
  HAS_KEY=false
  [[ -n "${ANTHROPIC_API_KEY:-}" ]] && HAS_KEY=true
  [[ -n "${OPENAI_API_KEY:-}" ]] && HAS_KEY=true

  if $HAS_KEY; then
    log "  Using LLM model: ${LLM_MODEL} (user turns only)"
    gitllm label "${CHAT_ID}" --model "${LLM_MODEL}" --role user --db "${GITLLM_DB}" \
      > "${RUN_DIR}/02-llm-labels.log" 2>&1

    gitllm export "${CHAT_ID}" "${RUN_DIR}/02-llm-labels.jsonl" --db "${GITLLM_DB}" \
      > /dev/null 2>&1

    qdb "
      SELECT t.idx, t.role, l.name AS label, l.master_class, l.labeler
      FROM turns t
      JOIN labels l ON l.turn_id = t.id
      WHERE t.chat_id = ${CHAT_ID}
      ORDER BY t.idx
    " > "${RUN_DIR}/02-llm-labels.json"
  else
    log "  No API key set - skipping LLM labeler (scorecard will mark N/A)"
    echo "skipped: no API key" > "${RUN_DIR}/02-llm-labels.log"
  fi
else
  log "  ❌ chat_id unresolved - labeling skipped"
fi

# =============================================================================
# Scenario 3 - Phases
# =============================================================================
log "Scenario 3: Phase compression"

if [[ -n "${CHAT_ID}" ]]; then
  gitllm phases "${CHAT_ID}" --db "${GITLLM_DB}" \
    > "${RUN_DIR}/03-phases.txt" 2>&1
fi

# =============================================================================
# Scenario 4 - Search recall (10 gold queries)
# =============================================================================
log "Scenario 4: Search recall"

# Search via CLI (Rich table output - human readable)
{
  echo "=== q1: jsonl decision ==="
  gitllm search --text 'jsonl fragile' --limit 5 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q2: pi schema ==="
  gitllm search --text 'pi-session-export' --limit 5 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q3: Directing label ==="
  gitllm search --label Directing --limit 10 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q4: Pivoting label ==="
  gitllm search --label Pivoting --limit 5 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q5: value proposition ==="
  gitllm search --text 'value proposition' --limit 5 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q6: Expositive + zettelkasten ==="
  gitllm search --class Expositive --text 'zettelkasten' --limit 5 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q7: Reflective label ==="
  gitllm search --label Reflective --limit 10 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q8: Providing-Context label ==="
  gitllm search --label "Providing-Context" --limit 5 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q9: parallel ==="
  gitllm search --text 'parallel' --limit 5 --db "${GITLLM_DB}" 2>&1 || true
  echo ""
  echo "=== q10: cross-chat Reflex ==="
  gitllm search --text 'Reflex' --limit 5 --db "${GITLLM_DB}" 2>&1 || true
} > "${RUN_DIR}/04-search.txt"

# Structured version for automated scoring (SQLite direct)
python3 - <<PY > "${RUN_DIR}/04-search.json"
import json

queries = [
    {"id": "q1",  "text": "jsonl fragile"},
    {"id": "q2",  "text": "pi-session-export"},
    {"id": "q5",  "text": "value proposition"},
    {"id": "q6",  "text": "zettelkasten", "master_class": "Expositive"},
    {"id": "q9",  "text": "parallel"},
    {"id": "q10", "text": "Reflex"},
]

import sqlite3, re as _re
conn = sqlite3.connect("${GITLLM_DB}")
conn.row_factory = sqlite3.Row

def _fts_quote(text):
    """Wrap in double quotes if the query contains FTS5 special chars (-, :, *)."""
    if _re.search(r'[-:*()]', text):
        return '"' + text.replace('"', '""') + '"'
    return text

results = []
for q in queries:
    text = _fts_quote(q.get("text", ""))
    mc = q.get("master_class")
    sql = """
        SELECT t.chat_id, t.idx, t.role, substr(t.content,1,200) AS snippet,
               COALESCE(GROUP_CONCAT(DISTINCT l2.name),'') AS labels,
               c.title AS chat_title
        FROM turns t
        JOIN chats c ON c.id = t.chat_id
        JOIN turns_fts f ON f.rowid = t.id
        LEFT JOIN labels l2 ON l2.turn_id = t.id
        WHERE f.content MATCH ?
    """
    params = [text]
    if mc:
        sql += " AND EXISTS (SELECT 1 FROM labels l WHERE l.turn_id = t.id AND l.master_class = ?)"
        params.append(mc)
    sql += " GROUP BY t.id ORDER BY t.chat_id, t.idx LIMIT 5"
    try:
        rows = conn.execute(sql, params).fetchall()
        results.append({
            "id": q["id"],
            "fts_query": text,
            "hits": [dict(r) for r in rows],
            "hit_count": len(rows),
        })
    except Exception as e:
        results.append({
            "id": q["id"],
            "fts_query": text,
            "error": str(e),
            "hit_count": 0,
        })
conn.close()
print(json.dumps(results, indent=2))
PY

# Label-filter queries (structured)
python3 - <<PY > "${RUN_DIR}/04-label-filter.json"
import sqlite3, json
conn = sqlite3.connect("${GITLLM_DB}")
conn.row_factory = sqlite3.Row

label_queries = [
    {"id": "q3", "label": "Directing"},
    {"id": "q4", "label": "Pivoting"},
    {"id": "q7", "label": "Reflective"},
    {"id": "q8", "label": "Providing-Context"},
]

results = []
for q in label_queries:
    rows = conn.execute("""
        SELECT t.chat_id, t.idx, t.role, substr(t.content,1,160) AS snippet
        FROM turns t
        JOIN labels l ON l.turn_id = t.id
        WHERE l.name = ?
        ORDER BY t.chat_id, t.idx
        LIMIT 20
    """, (q["label"],)).fetchall()
    results.append({"id": q["id"], "label": q["label"], "hits": [dict(r) for r in rows]})

conn.close()
print(json.dumps(results, indent=2))
PY

log "  Search results saved to 04-search.txt + 04-search.json + 04-label-filter.json"

# =============================================================================
# Scenario 5 - Extraction
# =============================================================================
log "Scenario 5: Extraction (Zettelkasten + ADRs)"

if [[ -n "${CHAT_ID}" ]]; then
  # Label first (may already be done in scenario 2)
  gitllm label "${CHAT_ID}" --model stub --db "${GITLLM_DB}" > /dev/null 2>&1 || true

  gitllm extract "${CHAT_ID}" --out "${RUN_DIR}/zettel" --db "${GITLLM_DB}" \
    > "${RUN_DIR}/05-extract.log" 2>&1

  # List all generated .md files (handle nested dirs like zettel/notes/)
  find "${RUN_DIR}/zettel" -name '*.md' -type f | sort \
    > "${RUN_DIR}/05-files.txt" 2>&1 || true

  # Dump extraction metadata for structured comparison
  python3 - <<PY > "${RUN_DIR}/05-artifacts.json"
import os, json, re
from pathlib import Path

zdir = Path("${RUN_DIR}/zettel")
artifacts = []
for f in sorted(zdir.rglob("*.md")):
    text = f.read_text(encoding="utf-8")
    # Extract YAML frontmatter
    fm = {}
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
    artifacts.append({
        "filename": f.name,
        "title": fm.get("title", f.stem),
        "kind": fm.get("kind", "unknown"),
        "source_turn": fm.get("source_turn", fm.get("source_chat_id", "unknown")),
        "line_count": len(text.splitlines()),
    })
print(json.dumps(artifacts, indent=2))
PY
fi

# =============================================================================
# Scenario 6 - Cross-chat
# =============================================================================
log "Scenario 6: Cross-chat capability"

# Search across ALL chats (no --chat filter)
gitllm search --text 'Reflex' --limit 10 --db "${GITLLM_DB}" \
  > "${RUN_DIR}/06-cross-reflex.txt" 2>&1 || true

gitllm search --text 'SQLModel' --limit 10 --db "${GITLLM_DB}" \
  > "${RUN_DIR}/06-cross-sqlmodel.txt" 2>&1 || true

# Structured: which chats returned hits?
python3 - <<PY > "${RUN_DIR}/06-cross-chat.json"
import sqlite3, json
conn = sqlite3.connect("${GITLLM_DB}")
conn.row_factory = sqlite3.Row

results = {}
for keyword in ["Reflex", "SQLModel"]:
    rows = conn.execute("""
        SELECT t.chat_id, t.idx, t.role, substr(t.content,1,200) AS snippet,
               c.title AS chat_title
        FROM turns t
        JOIN chats c ON c.id = t.chat_id
        JOIN turns_fts f ON f.rowid = t.id
        WHERE f.content MATCH ?
        ORDER BY t.chat_id, t.idx LIMIT 10
    """, (keyword,)).fetchall()
    results[keyword] = [dict(r) for r in rows]

# Verify chat ID stability (read from first import)
chat_ids = conn.execute("SELECT id, session_id FROM chats").fetchall()
results["_chat_id_stability"] = [dict(r) for r in chat_ids]

conn.close()
print(json.dumps(results, indent=2))
PY

# Scoped import test (dry-run for a repo we don't have)
gitllm import-pi --all --repo kuchnie --dry-run --db "${GITLLM_DB}" \
  > "${RUN_DIR}/06-scoped.log" 2>&1 || true

# =============================================================================
# Scenario 7 - Meta-test 🪞
# =============================================================================
log "Scenario 7: Meta-test (self-recognition)"

# Check if value-proposition (P10) and evaluation (P11) were extracted
find "${RUN_DIR}/zettel" -name '*.md' -type f 2>/dev/null | grep -iE 'value.prop|proposition' \
  > "${RUN_DIR}/07-met1-p10.txt" || true

find "${RUN_DIR}/zettel" -name '*.md' -type f 2>/dev/null | grep -iE 'evaluation|protocol' \
  > "${RUN_DIR}/07-met2-p11.txt" || true

# Parallel-write pattern: find all turns mentioning "parallel" with Directing label
python3 - <<PY > "${RUN_DIR}/07-met3-parallel.json"
import sqlite3, json
conn = sqlite3.connect("${GITLLM_DB}")
conn.row_factory = sqlite3.Row

# Find user turns with "parallel" in content AND labeled Directing
rows = conn.execute("""
    SELECT t.chat_id, t.idx, t.role, substr(t.content,1,200) AS snippet,
           GROUP_CONCAT(DISTINCT l.name) AS labels
    FROM turns t
    JOIN turns_fts f ON f.rowid = t.id
    LEFT JOIN labels l ON l.turn_id = t.id
    WHERE f.content MATCH 'parallel'
      AND t.role = 'user'
    GROUP BY t.id
    ORDER BY t.chat_id, t.idx
""").fetchall()

result = {
    "turns_mentioning_parallel": [dict(r) for r in rows],
    "count": len(rows),
    "directing_count": sum(1 for r in rows if "Directing" in (r["labels"] or "")),
}

import os
zdir = "${RUN_DIR}/zettel"
result["total_zettels_generated"] = sum(1 for _, _, files in os.walk(zdir) for f in files if f.endswith(".md")) if os.path.isdir(zdir) else 0

print(json.dumps(result, indent=2))
PY

# =============================================================================
# Summary
# =============================================================================
log "Done. Outputs in ${RUN_DIR}/"
log "Files produced:"
ls -1 "${RUN_DIR}" | while read -r f; do echo "  ${f}"; done

log "Next steps:"
echo "  1. Open docs/evaluation/scorecard.md alongside ${RUN_DIR}/"
echo "  2. Fill in scores per scenario."
echo "  3. (Optional) For an AI evaluator, feed ${RUN_DIR}/* + docs/evaluation/{rubric.yaml,gold/*}"
echo "     into your LLM and ask it to emit a scorecard.schema.json-conformant JSON."
