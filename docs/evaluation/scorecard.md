# Evaluation Scorecard

> Fill this in after running `bash docs/evaluation/run.sh`.
> Each section maps 1:1 to a scenario in `scenarios.md` and a block in `rubric.yaml`.

**Evaluator:** ______________________   **Date:** ______________
**Git SHA under test:** ______________ **Eval run dir:** `eval-run/_______`

---

## 1. Ingestion (weight 10%)

| Check | Result | Notes |
|---|:-:|---|
| ing.1 — both sessions imported | ⬜ pass / ⬜ fail | |
| ing.2 — session 2 has 11 user prompts | ⬜ pass / ⬜ fail | actual: ____ |
| ing.3 — parent chain preserved | ⬜ pass / ⬜ fail | |
| ing.4 — thinking blocks FTS-indexed | ⬜ pass / ⬜ fail | |
| ing.5 — idempotent re-import | ⬜ pass / ⬜ fail | |

**Scenario score:** ____ / 5  (≥4 to pass)

---

## 2. Labeling (weight 25%)

| Check | Result | Notes |
|---|:-:|---|
| lab.1 — no off-taxonomy labels | ⬜ pass / ⬜ fail | unknown labels: ____ |
| lab.2 — every turn labeled | ⬜ pass / ⬜ fail | null count: ____ |
| lab.3 — stub vs. human kappa | ____ | target ≥ 0.40 |
| lab.4 — LLM vs. human kappa  | ____ | target ≥ 0.60 |
| lab.5 — master-class agreement | ____ | target ≥ 0.70 |

**Per-prompt agreement table** (fill from `02-*-labels.jsonl` vs. `gold/session-2-prompts.yaml`):

| Prompt | Gold | Stub | LLM | Stub✓ | LLM✓ |
|:-:|---|---|---|:-:|:-:|
| P1 | Inquiring, Clarifying | _____ | _____ | ⬜ | ⬜ |
| P2 | Seeking-Validation, Challenging | _____ | _____ | ⬜ | ⬜ |
| P3 | Directing | _____ | _____ | ⬜ | ⬜ |
| P4 | Challenging, Pivoting | _____ | _____ | ⬜ | ⬜ |
| P5 | Providing-Context, Inquiring | _____ | _____ | ⬜ | ⬜ |
| P6 | Directing | _____ | _____ | ⬜ | ⬜ |
| P7 | Directing | _____ | _____ | ⬜ | ⬜ |
| P8 | Clarifying | _____ | _____ | ⬜ | ⬜ |
| P9 | Directing, Reflective | _____ | _____ | ⬜ | ⬜ |
| P10 | Directing, Reflective | _____ | _____ | ⬜ | ⬜ |
| P11 | Directing, Reflective | _____ | _____ | ⬜ | ⬜ |

Stub agreement: ____ / 11    LLM agreement: ____ / 11

---

## 3. Phases (weight 15%)

Expected boundaries after prompts: `[2, 3, 5, 8, 10]`
Actual boundaries (from `eval-run/03-phases.txt`): `[ ____ ]`

| Check | Result |
|---|:-:|
| phs.1 — ≥3 phases produced | ⬜ pass / ⬜ fail |
| phs.2 — boundary alignment (matched / 5) | ____ / 5 |
| phs.3 — narrative coherence (mean Likert 1–5) | ____ |

---

## 4. Search (weight 15%)

For each query in `gold/search-queries.yaml`:

| Query | Expected turn | Actual rank | Top-3? |
|---|---|:-:|:-:|
| q1 (jsonl decision) | P4 | ____ | ⬜ |
| q2 (pi schema) | P5 | ____ | ⬜ |
| q3 (Directing label) | P3, P6, P7, P9, P10, P11 | n/a | label filter ⬜ |
| q4 (Pivoting label) | P4 | ____ | ⬜ |
| q5 (value proposition) | P10 | ____ | ⬜ |
| q6 (Expositive + zettel) | P1 | ____ | ⬜ |
| q7 (Reflective label) | P9, P10, P11 | n/a | label filter ⬜ |
| q8 (Providing-Context) | P5 | ____ | ⬜ |
| q9 (parallel) | P6, P7 | ____ | ⬜ |
| q10 (cross-chat Reflex) | session-1 only | n/a | cross-chat ⬜ |

- Top-1 recall: ____ / 7    (target ≥ 0.5)
- Top-3 recall: ____ / 7    (target ≥ 0.8)
- Label filter precision: ⬜ pass / ⬜ fail
- Cross-chat: ⬜ pass / ⬜ fail

---

## 5. Extraction (weight 20%)

Files generated in `eval-run/zettel/`: __________

| Gold artifact | File found? | Phrases present? | Utility 1–5 |
|---|:-:|:-:|:-:|
| KN: Speech Act primer (P1) | ⬜ | ⬜ | ____ |
| KN: Pragmatic pipeline critique (P2) | ⬜ | ⬜ | ____ |
| KN: Value proposition + theory explainer (P10) | ⬜ | ⬜ | ____ |
| KN: Black-box evaluation protocol (P11) | ⬜ | ⬜ | ____ |
| ADR: JSONL canonical format (P4) | ⬜ | ⬜ | ____ |
| ADR: Pi-native schema (P5) | ⬜ | ⬜ | ____ |
| **PATTERN (bonus): parallel-write directive** | ⬜ | n/a | ____ |

- Recall = (found / 6) = ____
- Precision = (kept / generated) = ____
- Utility mean = ____
- False positives (anti-gold P8, P9 promoted?): ____

---

## 6. Cross-chat (weight 10%)

| Check | Result |
|---|:-:|
| crs.1 — search spans both chats | ⬜ pass / ⬜ fail |
| crs.2 — chat IDs stable across re-runs | ⬜ pass / ⬜ fail |
| crs.3 — `--repo` scope filter works | ⬜ pass / ⬜ fail |

---

## 7. Meta-test 🪞 (weight 5% bonus)

| Check | Result |
|---|:-:|
| met.1 — P10 (value prop turn) extracted as knowledge note | ⬜ pass / ⬜ fail |
| met.2 — P11 (this request) labeled [Directing] + [Structuring/Reflective] | ⬜ pass / ⬜ fail |
| met.3 — parallel-write pattern detected across P3/P6/P7 (Likert 1–5) | ____ |

> If checks 1+2 both pass, write below: *"The system extracted its own
> creation story."*

Evaluator comment: ________________________________________________

---

## Composite

| Scenario | Weight | Score (0–1) | Weighted |
|---|:-:|:-:|:-:|
| Ingestion | 0.10 | ____ | ____ |
| Labeling | 0.25 | ____ | ____ |
| Phases | 0.15 | ____ | ____ |
| Search | 0.15 | ____ | ____ |
| Extraction | 0.20 | ____ | ____ |
| Cross-chat | 0.10 | ____ | ____ |
| Meta-test (bonus) | 0.05 | ____ | ____ |
| **TOTAL** | 1.00 | | ____ |

**Grade:**  ⬜ 🟢 Green (≥0.80) ⬜ 🟡 Yellow (0.60–0.80) ⬜ 🔴 Red (<0.60)
**Veto triggered?** ⬜ no  ⬜ yes — reason: __________________

---

## Free-form findings

**Top 3 wins:**
1. ____________________
2. ____________________
3. ____________________

**Top 3 gaps:**
1. ____________________
2. ____________________
3. ____________________

**Recommended next iteration:** ____________________
