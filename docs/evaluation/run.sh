#!/usr/bin/env bash
# =============================================================================
# git-llm black-box evaluation driver
# =============================================================================
# Runs all 7 scenarios from docs/evaluation/scenarios.md against the pi.dev
# sessions for THIS repo. Produces eval-run/<timestamp>/ with all CLI outputs.
#
# No source-code introspection. Only `gitllm` CLI + standard unix tools.
# =============================================================================

set -uo pipefail   # NOTE: not -e — we WANT failures to record, not abort.

# -----------------------------------------------------------------------------
# 0. Setup
# -----------------------------------------------------------------------------
TS="$(date +%Y%m%dT%H%M%S)"
RUN_DIR="eval-run/${TS}"
mkdir -p "${RUN_DIR}/zettel"
ln -sfn "${TS}" eval-run/latest

export GITLLM_DB="${RUN_DIR}/db.sqlite"

GOLD_DIR="docs/evaluation/gold"
SESS_GLOB="$HOME/.pi/agent/sessions/--Users-michal-PycharmProjects-git-llm--/*.jsonl"

log() { echo -e "\n\033[1;34m[eval]\033[0m $*"; }
record() { tee -a "${RUN_DIR}/_journal.log" ; }

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

log "Eval run directory: ${RUN_DIR}"
log "DB: ${GITLLM_DB}"
log "Git SHA: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
  | tee "${RUN_DIR}/_git_sha.txt"

# -----------------------------------------------------------------------------
# Scenario 1 — Ingestion
# -----------------------------------------------------------------------------
log "Scenario 1: Ingestion correctness"
gitllm init                                                            > "${RUN_DIR}/01-init.log"           2>&1
gitllm import-pi --all --repo git-llm                                  > "${RUN_DIR}/01-ingest.log"         2>&1
gitllm import-pi --all --repo git-llm                                  > "${RUN_DIR}/01-reingest.log"       2>&1

# Capture verification queries
gitllm search --label Directing --json    > "${RUN_DIR}/01-verify-directing.json"    2>&1 || true
gitllm search --text 'parallel write' --json > "${RUN_DIR}/01-verify-parallel.json"  2>&1 || true
gitllm search --text 'pi-session-export' --json > "${RUN_DIR}/01-verify-pi.json"     2>&1 || true

# Determine the session-2 chat_id for downstream scenarios
CHAT_ID="$(gitllm search --text 'pi-session-export' --json 2>/dev/null \
            | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["chat_id"]) if d else print("")' \
            2>/dev/null || echo '')"
echo "${CHAT_ID}" > "${RUN_DIR}/_chat_id.txt"
log "Session-2 chat_id resolved to: ${CHAT_ID:-<unresolved>}"

# -----------------------------------------------------------------------------
# Scenario 2 — Labeling
# -----------------------------------------------------------------------------
log "Scenario 2: Labeling (stub + LLM)"
if [[ -n "${CHAT_ID}" ]]; then
  gitllm label "${CHAT_ID}" --labeler stub                             > "${RUN_DIR}/02-stub-labels.log"    2>&1
  gitllm export "${CHAT_ID}" --format jsonl                            > "${RUN_DIR}/02-stub-labels.jsonl"  2>&1

  if [[ -n "${OPENAI_API_KEY:-${ANTHROPIC_API_KEY:-}}" ]]; then
    gitllm label "${CHAT_ID}" --labeler llm --model gpt-4o-mini        > "${RUN_DIR}/02-llm-labels.log"     2>&1
    gitllm export "${CHAT_ID}" --format jsonl                          > "${RUN_DIR}/02-llm-labels.jsonl"   2>&1
  else
    log "  No API key set — skipping LLM labeler step (scorecard will mark N/A)"
    echo "skipped: no API key" > "${RUN_DIR}/02-llm-labels.log"
  fi
else
  log "  ❌ chat_id unresolved — labeling skipped"
fi

# -----------------------------------------------------------------------------
# Scenario 3 — Phases
# -----------------------------------------------------------------------------
log "Scenario 3: Phase compression"
if [[ -n "${CHAT_ID}" ]]; then
  gitllm phases "${CHAT_ID}"                                           > "${RUN_DIR}/03-phases.txt"         2>&1
fi

# -----------------------------------------------------------------------------
# Scenario 4 — Search
# -----------------------------------------------------------------------------
log "Scenario 4: Search recall (10 gold queries)"
{
  python3 - <<PY 2>/dev/null || echo "[]"
import yaml, json, subprocess, shlex
with open("${GOLD_DIR}/search-queries.yaml") as f:
    g = yaml.safe_load(f)
results = []
for q in g["queries"]:
    cmd = q["command"] + " --limit 5 --json"
    try:
        out = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=30)
        rows = json.loads(out.stdout) if out.stdout.strip().startswith("[") else []
    except Exception as e:
        rows = [{"error": str(e)}]
    results.append({"id": q["id"], "command": cmd,
                    "expected_prompts": q.get("expected_user_prompts", []),
                    "results": rows[:5]})
print(json.dumps(results, indent=2))
PY
} > "${RUN_DIR}/04-search.json"

# -----------------------------------------------------------------------------
# Scenario 5 — Extraction
# -----------------------------------------------------------------------------
log "Scenario 5: Extraction (Zettelkasten + ADRs)"
if [[ -n "${CHAT_ID}" ]]; then
  gitllm extract "${CHAT_ID}" --out "${RUN_DIR}/zettel"                > "${RUN_DIR}/05-extract.log"        2>&1
  ls -1 "${RUN_DIR}/zettel"                                            > "${RUN_DIR}/05-files.txt"          2>&1
fi

# -----------------------------------------------------------------------------
# Scenario 6 — Cross-chat
# -----------------------------------------------------------------------------
log "Scenario 6: Cross-chat capability"
gitllm search --text Reflex --json                                     > "${RUN_DIR}/06-cross-reflex.json"   2>&1
gitllm search --text SQLModel --json                                   > "${RUN_DIR}/06-cross-sqlmodel.json" 2>&1
gitllm import-pi --all --repo kuchnie --dry-run                        > "${RUN_DIR}/06-scoped.log"          2>&1

# -----------------------------------------------------------------------------
# Scenario 7 — Meta-test 🪞
# -----------------------------------------------------------------------------
log "Scenario 7: Meta-test (self-recognition)"
ls "${RUN_DIR}/zettel" 2>/dev/null | grep -iE 'value.prop|proposition' > "${RUN_DIR}/07-met1-p10.txt"        || true
ls "${RUN_DIR}/zettel" 2>/dev/null | grep -iE 'evaluation|protocol'   > "${RUN_DIR}/07-met2-p11.txt"        || true
gitllm search --text 'parallel write' --label Directing --json         > "${RUN_DIR}/07-met3-parallel.json"  2>&1

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
log "Done. Outputs in ${RUN_DIR}/"
log "Next steps:"
echo "  1. Open docs/evaluation/scorecard.md alongside ${RUN_DIR}/"
echo "  2. Fill in scores per scenario."
echo "  3. (Optional) For an AI evaluator, feed ${RUN_DIR}/* + docs/evaluation/{rubric.yaml,gold/*}"
echo "     into your LLM and ask it to emit a scorecard.schema.json-conformant JSON."
echo ""
echo "  Composite computation:"
echo "    python3 scripts/eval_aggregate.py --rubric docs/evaluation/rubric.yaml --scores ${RUN_DIR}/scorecard.json"
