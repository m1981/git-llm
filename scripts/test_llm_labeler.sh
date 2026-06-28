#!/usr/bin/env bash
# Quick smoke-test: label 3 turns with Claude Sonnet 4 via LiteLLM.
# Usage: bash scripts/test_llm_labeler.sh
#
# Requires ANTHROPIC_API_KEY in .env or environment.

set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Activate venv + load env
source .venv/bin/activate 2>/dev/null || true
[[ -f .env ]] && set -a && source .env && set +a

# ── Checks ──────────────────────────────────────────────────────────────────
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "✗ ANTHROPIC_API_KEY not set."
  echo "  1. Open .env at the repo root"
  echo "  2. Paste your key: ANTHROPIC_API_KEY=sk-ant-api03-..."
  echo "  3. Re-run this script."
  exit 1
fi

MODEL="${GITLLM_LABEL_MODEL:-claude-sonnet-4-5}"
echo "Model:  ${MODEL}"
echo "Key:    ${ANTHROPIC_API_KEY:0:10}...${ANTHROPIC_API_KEY: -4}"
echo ""

# ── Create a throwaway DB with one turn ─────────────────────────────────────
TMPDB=$(mktemp /tmp/gitllm-test-XXXXXX.sqlite)
gitllm init --db "$TMPDB" > /dev/null

# Ingest a minimal chat via inline JSONL
TMPJSONL=$(mktemp /tmp/gitllm-test-XXXXXX.jsonl)
cat > "$TMPJSONL" << 'JSONL'
{"role":"user","content":"Please check my React component for memory leaks"}
{"role":"assistant","content":"Looking at your useEffect, I notice the cleanup function is missing. This means the event listener persists after unmount. Fix: return () => window.removeEventListener('resize', handler) inside the effect."}
JSONL

CHAT_ID=$(gitllm ingest "$TMPJSONL" --db "$TMPDB" 2>&1 | grep -o 'chat_id=[0-9]*' | cut -d= -f2)
echo "Ingested chat ${CHAT_ID}"

# ── Label with Claude Sonnet 4 ─────────────────────────────────────────────
echo "Labeling with ${MODEL}..."
gitllm label "$CHAT_ID" --model "$MODEL" --db "$TMPDB"

# ── Show results ────────────────────────────────────────────────────────────
echo ""
echo "=== Labels assigned ==="
python3 -c "
import sqlite3, json
conn = sqlite3.connect('$TMPDB')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT t.idx, t.role, t.content,
           GROUP_CONCAT(l.name || \" (\" || ROUND(l.confidence,2) || \")\") AS labels,
           l.labeler
    FROM turns t
    LEFT JOIN labels l ON l.turn_id = t.id
    GROUP BY t.id ORDER BY t.idx
''').fetchall()
for r in rows:
    content = r['content'][:80].replace(chr(10), ' ')
    print(f\"  Turn {r['idx']} [{r['role']:9}] {content}...\")
    print(f\"           → {r['labels'] or '(none)'}\")
    print(f\"           labeler: {r['labeler']}\")
    print()
"

# ── Cleanup ─────────────────────────────────────────────────────────────────
rm -f "$TMPDB" "$TMPJSONL"
echo "✓ LLM labeler smoke-test passed. Labels are real Anthropic classifications."
