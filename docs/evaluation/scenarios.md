# Evaluation Scenarios (Runnable)

Each scenario is **runnable in isolation** and **black-box** — the only inputs
are `gitllm` CLI commands; the only outputs are stdout, generated files, and
the SQLite database (queried through the CLI).

> Run the full suite via `bash docs/evaluation/run.sh`.
> Outputs land in `eval-run/<timestamp>/`.

---

## Scenario 1 — Ingestion correctness (objective)

**Goal:** Verify both pi.dev sessions ingest losslessly.

```bash
# Setup: fresh DB
rm -f eval-run/db.sqlite
export GITLLM_DB=eval-run/db.sqlite
gitllm init

# Import everything for this repo
gitllm import-pi --all --repo git-llm > eval-run/01-ingest.log

# Re-run to test idempotency
gitllm import-pi --all --repo git-llm > eval-run/01-reingest.log
```

**Expected:**
- `01-ingest.log` reports `discovered=2, imported=2, skipped=0, failed=0`
- `01-reingest.log` reports `discovered=2, imported=0, skipped=2, failed=0`
- Session 2 has exactly **11 user prompts** (verifiable via search)

**Verification commands (these go in the scorecard):**
```bash
gitllm search --label Directing | wc -l         # >= 5 expected
gitllm search --text 'parallel write'           # P6/P7 must surface
gitllm search --text 'pi-session-export'        # P5 must surface
```

**Diagnose if fails:**
- Counts off → pi adapter doesn't dedupe by `session_id`, or skips tool turns.
- Parent chain broken → check `parentId → parent_id` mapping in `pi_import.py`.

---

## Scenario 2 — Labeling quality (subjective + objective)

**Goal:** Compare StubLabeler and LLMLabeler against `gold/session-2-prompts.yaml`.

```bash
CHAT_ID=$(gitllm search --text 'pi-session-export' --json | jq -r '.[0].chat_id')

# Run heuristic labeler
gitllm label $CHAT_ID --labeler stub > eval-run/02-stub-labels.log

# Snapshot per-turn labels
gitllm export $CHAT_ID --format jsonl > eval-run/02-stub-labels.jsonl

# Run LLM labeler (requires API key; skip if unavailable)
gitllm label $CHAT_ID --labeler llm --model gpt-4o-mini > eval-run/02-llm-labels.log
gitllm export $CHAT_ID --format jsonl > eval-run/02-llm-labels.jsonl
```

**Scoring procedure (human or AI evaluator):**

1. For each of the 11 user prompts in `gold/session-2-prompts.yaml`, compare
   `gold_labels` vs. what the stub/LLM labeler assigned.
2. Compute simple agreement (matching label count / 11) per labeler.
3. Compute Austin master-class agreement (coarser, should be higher).
4. Optional: Cohen's kappa via:
   ```bash
   python3 scripts/eval_kappa.py \
     --gold docs/evaluation/gold/session-2-prompts.yaml \
     --pred eval-run/02-llm-labels.jsonl
   ```

**Pass thresholds:**
- Stub labeler ≥ 0.40 agreement
- LLM labeler ≥ 0.60 agreement
- Master-class agreement ≥ 0.70

**Diagnose if fails:**
- Off-taxonomy labels appearing → labeler prompt isn't constraining output.
- Bias toward one label (e.g., everything tagged `Inquiring`) → label set
  imbalanced; consider few-shot examples.

---

## Scenario 3 — Phase compression (subjective)

**Goal:** Does `gitllm phases` produce a narrative arc matching `gold/expected-phases.yaml`?

```bash
gitllm phases $CHAT_ID > eval-run/03-phases.txt
```

**Scoring procedure:**

1. Open `eval-run/03-phases.txt` and `gold/expected-phases.yaml` side-by-side.
2. For each of the 5 expected boundaries (`[2, 3, 5, 8, 10]`):
   - ✅ Matched if a phase boundary falls within ±1 user prompt.
3. Rate narrative coherence per phase (1–5 Likert).

**Pass thresholds:**
- ≥ 3/5 boundaries matched
- Mean narrative coherence ≥ 3.5

**Diagnose if fails:**
- All turns merged into one phase → adjacency-pair window too wide.
- Each turn its own phase → window too narrow; tune `phases.py`.

---

## Scenario 4 — Search recall (objective)

**Goal:** Run all 10 queries in `gold/search-queries.yaml`, check top-3 recall.

```bash
while read -r q cmd ; do
  echo "=== $q ==="
  eval "$cmd --limit 3 --json"
done < <(yq -r '.queries[] | "\(.id) \(.command)"' docs/evaluation/gold/search-queries.yaml) \
  > eval-run/04-search.json
```

**Scoring:**

| Metric | Formula | Target |
|---|---|---|
| Top-1 recall | (# queries where expected turn is rank 1) / 10 | ≥ 0.5 |
| Top-3 recall | (# queries where expected turn is in top 3) / 10 | ≥ 0.8 |
| Label filter precision | (# returned turns matching filter) / (# returned) | 1.0 |

**Diagnose if fails:**
- FTS missing turns → check that thinking-block content is indexed.
- Label filter returning off-class turns → join on labels table is wrong.

---

## Scenario 5 — Extraction precision/recall (subjective)

**Goal:** Generate Zettelkasten notes + ADRs, compare to `gold/expected-artifacts.yaml`.

```bash
mkdir -p eval-run/zettel
gitllm extract $CHAT_ID --out eval-run/zettel > eval-run/05-extract.log
ls eval-run/zettel/ > eval-run/05-files.txt
```

**Scoring procedure:**

1. **Recall:** For each of the 6 gold artifacts in `expected-artifacts.yaml`,
   check if a matching file exists (title fuzzy-match + `must_contain_phrases`
   present). Score = matched / 6.
2. **Precision:** For each generated file NOT in gold, ask:
   *"Would I save this to Obsidian?"* If yes → still counts as precision pass.
   Anti-gold list flags false positives.
3. **Utility:** Rate each generated file 1–5. Mean ≥ 3.5 to pass.

**Pass thresholds:**
- Recall ≥ 0.6
- Precision ≥ 0.7
- Mean utility ≥ 3.5

**Diagnose if fails:**
- Empty output → trigger rules in `extract.py` too strict, or labels missing.
- Junk output → triggers too loose; tighten label combinations required.

---

## Scenario 6 — Cross-chat capability (objective)

**Goal:** Verify the tool works as a multi-chat knowledge bank.

```bash
# Searches without --chat-id should span both sessions
gitllm search --text Reflex --json > eval-run/06-cross-reflex.json
gitllm search --text SQLModel --json > eval-run/06-cross-sqlmodel.json

# Scoped imports
gitllm import-pi --all --repo kuchnie --dry-run > eval-run/06-scoped.log
```

**Expected:**
- `06-cross-reflex.json` returns hits primarily from session 1 (Reflex was
  discussed there) — proves cross-chat retrieval.
- `06-scoped.log` shows zero git-llm sessions imported (scope filter works).

**Diagnose if fails:**
- Scope leakage → `--repo` filter ignored.

---

## Scenario 7 — Meta-test 🪞 (the dogfood proof)

**Goal:** Verify the system can read its own creation story.

```bash
# Check that the value-proposition turn (P10) generated a knowledge note
ls eval-run/zettel/ | grep -i 'value-prop\|proposition'

# Check that the current request (P11) generated an artifact
ls eval-run/zettel/ | grep -i 'evaluation\|protocol'

# Check that the parallel-write pattern was detected (P3, P6, P7 share label)
gitllm search --text 'parallel write' --label Directing --json \
  > eval-run/07-parallel-pattern.json
```

**Scoring:**

| Check | Pass criteria |
|---|---|
| P10 → knowledge note generated | Yes/No |
| P11 → knowledge note generated | Yes/No |
| Parallel-write pattern surfaces ≥ 2 turns | Yes/No |
| Pattern detected as repeated theme (bonus) | Likert 1–5 |

**If 3/3 binary checks pass: the system has demonstrated reflexive
self-recognition on its own creation corpus.** That is the strongest
empirical signal this evaluation can produce.

---

## Aggregation

After running all scenarios, the human/AI evaluator fills in
[`scorecard.md`](scorecard.md) (or `scorecard.schema.json`). The composite
score uses the weights from `rubric.yaml`.

```bash
# Optional: auto-aggregate from a filled scorecard
python3 scripts/eval_aggregate.py \
  --rubric docs/evaluation/rubric.yaml \
  --scores eval-run/scorecard.json \
  > eval-run/composite.txt
```
