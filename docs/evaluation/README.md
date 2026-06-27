# Evaluation Protocol — Black-Box Dogfood

> **The premise:** the pi.dev session files that *produced* `git-llm` are the
> fairest possible test corpus. If the tool can find, label, summarize, and
> extract knowledge from its own creation story, it works.

This folder defines a **black-box evaluation** of the `git-llm` CLI.
"Black-box" means: no inspecting source code, no calling Python APIs.
Only `gitllm <command>` invocations and inspection of their outputs
(stdout, generated files, SQLite query results via the CLI).

---

## What gets evaluated

| # | Dimension | Objective? | Weight |
|---|---|---|---|
| 1 | **Ingestion correctness** | ✅ fully | 10% |
| 2 | **Labeling quality** | ⚠️ vs. human gold | 25% |
| 3 | **Phase compression** | ⚠️ vs. narrative gold | 15% |
| 4 | **Search recall** | ✅ top-N retrieval | 15% |
| 5 | **Extraction precision/recall** | ⚠️ vs. artifact gold | 20% |
| 6 | **Cross-chat capability** | ✅ idempotency + scope | 10% |
| 7 | **Meta-test (self-recognition)** 🪞 | ⚠️ qualitative | 5% bonus |

Weights are advisory — the protocol produces a per-dimension score plus an
overall composite.

---

## The corpus

```
~/.pi/agent/sessions/--Users-michal-PycharmProjects-git-llm--/
├── 2026-06-27T15-01-05-061Z_…1.jsonl   (196 lines — bootstrap session)
└── 2026-06-27T23-23-21-638Z_…2.jsonl   (213 lines — design session, in-progress)
```

These two sessions cover:
- Initial concept exploration (Speech Acts, MIDAS, Zettelkasten)
- Critique of the AI's drift toward theory
- Implementation of the full pipeline
- Source-format pivot (markdown → JSONL → pi-native)
- The value-proposition document write-up
- *This evaluation request itself* (P11 of session 2)

**Session 2 user-prompt gold list** (objectively verified — 11 prompts):
see [`gold/session-2-prompts.yaml`](gold/session-2-prompts.yaml).

---

## File layout

```
docs/evaluation/
├── README.md                       ← this file (the protocol)
├── rubric.yaml                     ← single-source-of-truth scoring criteria
├── scenarios.md                    ← 7 runnable scenarios (bash + expected)
├── gold/
│   ├── session-2-prompts.yaml      ← objective: 11 user prompts in order
│   ├── expected-phases.yaml        ← narrative gold (phase boundaries)
│   ├── expected-artifacts.yaml     ← gold zettels & ADRs the extractor should produce
│   └── search-queries.yaml         ← 10 NL queries with expected answer turns
├── scorecard.md                    ← markdown form for human evaluators
├── scorecard.schema.json           ← JSON shape for AI evaluators
└── run.sh                          ← one-shot driver: runs all scenarios, dumps outputs
```

---

## How to run it (human, ~30 min)

```bash
# 1. Run the driver — produces ./eval-run/<timestamp>/{outputs,artifacts,db.sqlite}
bash docs/evaluation/run.sh

# 2. Open the scorecard alongside the outputs
$EDITOR docs/evaluation/scorecard.md eval-run/latest/

# 3. For each scenario, compare actual outputs to gold files, fill in scores.
# 4. Total at the bottom.
```

## How to run it (AI evaluator)

```bash
bash docs/evaluation/run.sh
# Then feed these to the LLM:
#   - docs/evaluation/rubric.yaml
#   - docs/evaluation/gold/*.yaml
#   - eval-run/latest/* (the actual CLI outputs)
# Ask: "Fill in scorecard.schema.json per the rubric."
```

The LLM produces a `scorecard.json` with the same structure as the human
scorecard, enabling **head-to-head comparison of human and AI judgements**
(meta-meta: this is itself a labeling-agreement experiment).

---

## Design principles

1. **One rubric, two surfaces.** `rubric.yaml` drives both the human Markdown
   form and the AI JSON schema. No drift.
2. **Gold files are versioned.** When the tool changes, gold can be updated
   in git with a clear diff of what *should* change.
3. **Idempotent corpus.** Pi sessions are append-only; re-running the eval
   yields stable results until the corpus grows.
4. **Failure is informative.** Every scenario has a "diagnose" section
   listing the likely cause if the expected output doesn't match.
5. **No hidden state.** All inputs (corpus, gold, rubric) and outputs
   (`eval-run/`) live in the filesystem and are inspectable.

---

## What "passing" means

- **🟢 Green (>0.80 composite):** ship-ready for personal use.
- **🟡 Yellow (0.60–0.80):** usable but needs labeler / extractor tuning.
- **🔴 Red (<0.60):** taxonomy or pipeline has fundamental gaps; iterate.

A single dimension scoring below 0.40 is a **veto** regardless of composite —
e.g. if extraction is unreliable, the whole value chain breaks.

---

## The Meta-Test (Scenario 7) 🪞

> *Run the evaluation on session 2. Does the system extract the
> value-proposition writing turn (P10) as a knowledge note? Does it
> identify the current evaluation request (P11) as a [Directing]
> + [Structuring] act? Does it cluster P3 + P6 + P7 (all parallel-write
> directives) as a behavioral pattern?*

If yes, **the system has demonstrated it can read its own creation story**.
That's the strongest empirical claim a dogfood evaluation can make.

---

See [`scenarios.md`](scenarios.md) for the executable test scripts.
