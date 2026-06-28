# Evaluation Specifications — Unimplemented Features

> Three evaluation designs for the roadmap features:
> inter-labeler agreement, backlink resolution, cross-chat clustering.
>
> Each follows the same format as `scenarios.md`: rubric criteria,
> gold data, runnable test, and scorecard integration.

---

## 8. Inter-Labeler Agreement

**Goal:** Measure how consistently the stub and LLM labelers classify the same turns.

### Why it matters

If two labelers agree on 90% of turns, the pipeline is reliable.
If they agree on 50%, one of them is broken. The user needs to know
which labeler to trust — and whether the stub labeler is "good enough"
to use when no API key is available.

### Design

```
                    ┌─────────┐
                    │  Turn N  │
                    └────┬────┘
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         ┌────────┐ ┌────────┐ ┌────────┐
         │  Stub  │ │  LLM   │ │ Human  │
         │ Labeler│ │ Labeler│ │  Gold  │
         └───┬────┘ └───┬────┘ └───┬────┘
             │          │          │
             ▼          ▼          ▼
         Labels A    Labels B   Labels C
             │          │          │
             └────┬─────┘────┬─────┘
                  ▼          ▼
            κ(stub,LLM)  κ(stub,gold)
            κ(LLM,gold)
```

Three pairwise comparisons:
- **κ(stub, LLM)** — how much do the automated labelers agree?
- **κ(stub, human)** — is the stub labeler accurate?
- **κ(LLM, human)** — is the LLM labeler accurate?

### Rubric

```yaml
inter_labeler_agreement:
  weight: 0.15  # new dimension, additive to existing composite
  checks:
    - id: ila.1
      name: stub_vs_llm_kappa
      check: "Cohen's kappa, stub vs LLM on 20-turn sample"
      target: 0.40  # "moderate" agreement

    - id: ila.2
      name: llm_vs_human_kappa
      check: "Cohen's kappa, LLM vs human gold"
      target: 0.60  # "good" agreement

    - id: ila.3
      name: stub_vs_human_kappa
      check: "Cohen's kappa, stub vs human gold"
      target: 0.30  # "fair" — stub is heuristic, lower bar

    - id:ila.4
      name: master_class_agreement
      check: "Austin master-class agreement (coarser, should be higher)"
      target: 0.70

    - id: ila.5
      name: label_bias
      check: "No single label accounts for >40% of LLM assignments"
      score: pass_fail
```

### Gold data

File: `gold/label-gold.yaml`

```yaml
session_id: "019f0b65-149c-7528-8c8b-1f754cc9d84a"
evaluator: "human"
instructions: |
  For each user prompt, assign 1–3 labels from the 20-label dictionary.
  Use your judgement — there is no single "correct" answer.
  When unsure, prefer fewer labels over more.

turns:
  - idx: 0
    content: "Please tellm what are those concepts about"
    gold_labels: [Inquiring, Clarifying]

  - idx: 2
    content: "Please look on my problem (uaser) and AI thinking..."
    gold_labels: [Seeking-Validation, Challenging]

  # ... (all 20 user turns from session 2)
```

### Runnable test

```bash
# 1. Ensure both labelers have run (done in evaluation run.sh)
# 2. Compute agreement
python3 scripts/eval_kappa.py \
  --gold docs/evaluation/gold/label-gold.yaml \
  --db eval-run/latest/db.sqlite \
  --chat-id 2
```

Output:
```
Pairwise Cohen's Kappa:
  stub  vs LLM   : κ = 0.38 (fair)
  stub  vs human : κ = 0.31 (fair)
  LLM   vs human : κ = 0.62 (good)
  master-class   : κ = 0.71 (good)

Label bias (LLM):
  Directing: 32%  ← within threshold
  Analytical: 18%
  ...
```

### Implementation plan

```python
# scripts/eval_kappa.py
# - Load gold from YAML
# - Load stub labels from DB (labeler='stub')
# - Load LLM labels from DB (labeler='llm:claude-sonnet-4-5')
# - For each turn: compute pairwise label agreement
# - Cohen's kappa: sklearn.metrics.cohen_kappa_score (or manual)
# - Output table + pass/fail per check
```

---

## 9. Backlink Resolution

**Goal:** Extracted zettels should reference each other when they share concepts,
creating a navigable graph instead of isolated notes.

### Why it matters

The Zettelkasten method's power comes from **links between notes**, not from
notes in isolation. A note about "Clean Architecture" that links to a note
about "connection pooling" and a note about "Reflex framework" creates a
knowledge graph that compounds over time.

### Current state

Zettels currently have:
```yaml
id: 20260628101638-all-green-here-is-what-was-delivered
source_chat: 2
source_turns: [18]
labels: [Correcting, Pragmatic, Prescriptive, Structuring, Warning]
```

They do NOT have:
```yaml
related:
  - 20260628101638-document-structure
  - 20260628101638-everything-is-in-place
links_to:
  - id: 20260628101638-document-structure
    reason: "shared labels: Structuring"
```

### Design

Two levels of backlinking:

**Level 1 — Label overlap (deterministic):**
Zettels that share ≥2 labels get bidirectional `related:` links.

**Level 2 — Content proximity (embedding-based):**
Zettels whose content embeddings are within cosine similarity 0.7
get `related:` links. Requires an embedding model (future).

### Rubric

```yaml
backlink_resolution:
  weight: 0.10
  checks:
    - id: blk.1
      name: every_zettel_has_related
      check: "Every extracted zettel has ≥1 related: entry"
      score: pass_fail

    - id: blk.2
      name: bidirectional_links
      check: "If A links to B, then B links to A"
      score: pass_fail

    - id: blk.3
      name: link_precision
      check: "Of generated links, fraction where both zettels share ≥1 label"
      target: 0.80

    - id: blk.4
      name: link_recall
      check: "Of zettel pairs sharing ≥2 labels, fraction that are linked"
      target: 0.70

    - id: blk.5
      name: graph_connectivity
      check: "Zettel graph has no isolated nodes (degree ≥1 for all)"
      score: pass_fail
```

### Gold data

File: `gold/expected-backlinks.yaml`

```yaml
# For the git-llm session's 12 zettels, specify expected links.
# A link is expected when two zettels share ≥2 labels.

session_id: "019f0b65-149c-7528-8c8b-1f754cc9d84a"

expected_links:
  # Turn 1 (Educational, Pragmatic, Prescriptive, Structuring)
  # Turn 89 (Educational, Structuring)
  # Shared: Educational, Structuring → link
  - from: "turn-1"
    to: "turn-89"
    reason: "shared: Educational, Structuring"

  # Turn 18 (Correcting, Pragmatic, Prescriptive, Structuring, Warning)
  # Turn 30 (Prescriptive, Warning)
  # Shared: Prescriptive, Warning → link
  - from: "turn-18"
    to: "turn-30"
    reason: "shared: Prescriptive, Warning"

  # ... (all expected pairs)
```

### Runnable test

```bash
python3 scripts/eval_backlinks.py \
  --db eval-run/latest/db.sqlite \
  --chat-id 2 \
  --zettel-dir eval-run/latest/zettel-clean/notes/
```

Output:
```
Backlink Resolution:
  Zettels: 12
  Links generated: 18
  Bidirectional: 18/18 (100%)
  Link precision: 15/18 (83%) ≥ 0.80 ✅
  Link recall: 8/10 (80%) ≥ 0.70 ✅
  Isolated nodes: 0 ✅
  Graph connectivity: PASS
```

### Implementation plan

```python
# In extract.py — add _resolve_backlinks():
def _resolve_backlinks(artifacts: list[ExtractedArtifact]) -> None:
    """Add related: links between zettels sharing ≥2 labels."""
    for i, a in enumerate(artifacts):
        for j, b in enumerate(artifacts):
            if i >= j:
                continue
            shared = set(a.labels) & set(b.labels)
            if len(shared) >= 2:
                a.related.append(b.zk_id)
                b.related.append(a.zk_id)

# In render_markdown() — add related: to frontmatter:
frontmatter["related"] = artifact.related or []
```

---

## 10. Cross-Chat Clustering

**Goal:** Group zettels from different chats by concept similarity, so
"Clean Architecture" notes from the kuchnie session link to "Clean Architecture"
notes from the git-llm session.

### Why it matters

The user's knowledge spans multiple projects. A design decision made in
kuchnie ("use SQLModel") might be relevant to a future project. Without
cross-chat clustering, each project's knowledge is an island.

### Design

Three approaches, ordered by complexity:

**Approach A — Label overlap (no ML):**
Zettels from different chats that share ≥2 labels are in the same cluster.
Simple, deterministic, no embeddings needed.

**Approach B — TF-IDF cosine similarity:**
Compute TF-IDF vectors over zettel content, then cluster with agglomerative
clustering (threshold 0.3). Works without an embedding model.

**Approach C — Embedding similarity:**
Use a sentence-transformer model to embed zettel content, then cluster.
Best quality but requires an ML model.

### Rubric

```yaml
cross_chat_clustering:
  weight: 0.10
  checks:
    - id: ccc.1
      name: clusters_found
      check: "≥2 clusters identified across ≥2 chats"
      score: pass_fail

    - id: ccc.2
      name: cluster_coherence
      check: "Mean intra-cluster label overlap ≥ 0.3"
      target: 0.30

    - id: ccc.3
      name: cross_chat_links
      check: "≥1 cluster contains zettels from ≥2 different chats"
      score: pass_fail

    - id: ccc.4
      name: no_singleton_clusters
      check: "≤20% of clusters contain only 1 zettel"
      target: 0.80
```

### Gold data

File: `gold/expected-clusters.yaml`

```yaml
# For the combined git-llm + kuchnie zettels, specify expected clusters.
# A cluster is a group of zettels that share a concept.

expected_clusters:
  - id: architecture
    concept: "Software architecture and design patterns"
    zettels:
      - chat: git-llm, turn: 1   # "Overview of Concepts"
      - chat: git-llm, turn: 89  # "Document Structure"
      - chat: kuchnie, turn: 4   # Architecture synthesis

  - id: implementation
    concept: "Code implementation and testing"
    zettels:
      - chat: git-llm, turn: 30  # "26 tests pass"
      - chat: git-llm, turn: 54  # "import-pi shipped"
      - chat: kuchnie, turn: 85  # "back panel height per code"

  - id: decisions
    concept: "Architectural decisions and trade-offs"
    zettels:
      - chat: git-llm, turn: 18  # "All green, delivered"
      - chat: git-llm, turn: 102 # "Everything in place"
      - chat: kuchnie, turn: 113 # Documentation approach
```

### Runnable test

```bash
python3 scripts/eval_clusters.py \
  --dbs eval-run/latest/db.sqlite /tmp/meta-test-kuchnie.sqlite \
  --chat-ids 2 1 \
  --method label-overlap
```

Output:
```
Cross-Chat Clustering (label-overlap):
  Total zettels: 31 (12 git-llm + 19 kuchnie)
  Clusters found: 4
  Cross-chat clusters: 3/4 (75%) ✅
  Mean coherence: 0.42 ≥ 0.30 ✅
  Singleton clusters: 1/4 (25%) — borderline

  Cluster 1: "architecture" (5 zettels, 2 chats)
    - git-llm#1: Overview of Concepts
    - git-llm#89: Document Structure
    - kuchnie#4: Architecture synthesis
    - kuchnie#113: Documentation approach
    - kuchnie#68: Build summary

  Cluster 2: "implementation" (4 zettels, 2 chats)
    - git-llm#30: 26 tests pass
    - git-llm#54: import-pi shipped
    - kuchnie#85: back panel height
    - kuchnie#38: walking skeleton validation
```

### Implementation plan

```python
# scripts/eval_clusters.py
# Phase 1 (label-overlap, no ML):
#   1. Load zettels from both DBs
#   2. Build label vectors (binary: which labels each zettel has)
#   3. Compute pairwise Jaccard similarity
#   4. Agglomerative clustering (threshold 0.3)
#   5. Evaluate: coherence, cross-chat ratio, singletons
#
# Phase 2 (TF-IDF, optional):
#   1. Load zettel content
#   2. TF-IDF vectorization (sklearn)
#   3. Cosine similarity matrix
#   4. Same clustering + evaluation
```

---

## Summary: Three New Evaluation Dimensions

| # | Dimension | Method | ML Required? | Blocking? |
|---|---|---|---|---|
| 8 | Inter-labeler agreement | Cohen's κ (stub vs LLM vs human) | No | Yes — validates taxonomy |
| 9 | Backlink resolution | Label overlap → bidirectional links | No (Phase 1) | No — enhancement |
| 10 | Cross-chat clustering | Jaccard similarity → agglomerative | No (Phase 1) | No — enhancement |

**Recommended implementation order:**

1. **Inter-labeler agreement** (scripts/eval_kappa.py) — highest value, no feature code needed
2. **Backlink resolution** (extract.py changes) — small code change, high Zettelkasten value
3. **Cross-chat clustering** (scripts/eval_clusters.py) — standalone script, no pipeline changes

All three can be implemented as **evaluation scripts first** (measure current state),
then the feature code can be added to improve the scores.
