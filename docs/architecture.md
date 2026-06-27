# Architecture

> Design rationale for `git-llm`.

## 1. Problem framing

The user's `docs/initial-conversation.md` exposes a real operational problem
(recall / navigation / signal-vs-noise / extraction across many LLM chats) and
proposes a 20-label taxonomy as the solution. Critique: a taxonomy is *one
column* in the system you need; the pipeline around it (capture, store, query,
extract) is the bulk of the work and was missing.

`git-llm` implements that pipeline.

## 2. Core decisions

### ADR-001: SQLite + FTS5 over a graph DB or Elasticsearch
- **Status:** Accepted
- **Context:** Personal-scale: ~10²–10³ chats × ~40 turns. Single user, local-first.
- **Decision:** SQLite with FTS5 (porter + unicode61 tokenizer).
- **Consequences:** Zero ops, single file, trivial backup, fast enough for
  10⁵ turns. Cost: no native graph queries — backlinks are modeled as a
  flat `artifact_links` table, which is adequate for Zettelkasten-style use.

### ADR-002: Keep the user's 20 labels; add Austin class as a column
- **Status:** Accepted
- **Context:** The user already has cognitive investment in 20 labels. A switch
  to MIDAS (~23) or SwDA (~42) mid-project would be churn.
- **Decision:** Persist `name` *and* `master_class` per label row. Store a
  `midas_hint` in code (not DB) for future migration.
- **Consequences:** Both axes are queryable (`--label Warning` or
  `--class Verdictive`). Migration to MIDAS is a SQL update, not a redesign.

### ADR-003: Pluggable Labeler protocol with offline stub
- **Status:** Accepted
- **Context:** Tests and air-gapped use must not require an API key.
- **Decision:** `Labeler` protocol with two implementations: `StubLabeler`
  (regex heuristics) and `LLMLabeler` (LiteLLM → any provider).
- **Consequences:** `pytest` is hermetic. Users pay only for production
  labeling. Labelers are tagged in the `labels.labeler` column, so multiple
  labelers can coexist (enables inter-annotator agreement later).

### ADR-004: Rule-based extraction over LLM-summarization
- **Status:** Accepted
- **Context:** LLM summarization is non-deterministic, expensive, and hides
  the labeling logic.
- **Decision:** Extraction triggers are explicit `(kind, label-set)` rules in
  `taxonomy.py`. Body content is the raw turn text — no summarization in v1.
- **Consequences:** Reproducible. The output of `extract` depends only on
  labels in the DB. LLM-based distillation can be added later as a separate
  `distill` command without touching extraction.

### ADR-005: Markdown + YAML frontmatter for Zettel notes
- **Status:** Accepted
- **Context:** Must integrate with Obsidian, Logseq, plain `grep`.
- **Decision:** Each note = `<zk_id>.md` with YAML frontmatter
  (`id`, `kind`, `source_chat`, `source_turns`, `labels`).
- **Consequences:** Tool-agnostic. Backlinks (`[[zk_id]]`) can be inserted
  by future enrichment without changing the storage format.

## 3. Data model

```
chats (id, title, source, created_at, raw_path)
  └── turns (id, chat_id, idx, role, content, token_estimate)
        ├── labels (turn_id, name, master_class, confidence, labeler)
        └── turns_fts (FTS5 mirror of content, kept in sync by triggers)
artifacts (id, chat_id, kind, title, body, zk_id, turn_start..end, labels, file_path)
  └── artifact_links (artifact_id, linked_zk_id)
```

The `labels` UNIQUE constraint is `(turn_id, name, labeler)` — the same turn
can have the same label from multiple labelers, enabling agreement studies.

## 4. Module dependency rules

```
cli ──▶ ingest, label, search, phases, extract
                │           │       │       │
                ▼           ▼       ▼       ▼
              models ◀──── db ◀──── taxonomy
```

- `taxonomy.py` and `models.py` are pure (no DB, no IO).
- `db.py` owns the schema; only `ingest`, `label`, `extract`, `search`, `phases`
  may execute SQL.
- `cli.py` is the only module that talks to the user (stdout/stderr).

## 5. Testing strategy

- **Hermetic**: every test gets a fresh tmp SQLite via the `tmp_db` fixture.
- **Dogfood**: the real `docs/initial-conversation.md` is the canonical fixture.
- **No network**: `StubLabeler` runs in CI; `LLMLabeler` is exercised by
  manual smoke tests only.

## 6. Roadmap

### v0.2 — Infelicity Report
The user's second proposal introduced *Infelicity Reports* (quarantining
dead branches). Implement as: detect contiguous runs of `[Correcting]` or
`[Pivoting]` that are later overturned by a later `[Pivoting]`. Mark those
turn ranges as `is_infelicity = TRUE`. CLI: `gitllm infelicities <chat>`.

### v0.3 — Inter-labeler agreement
Run `StubLabeler` and `LLMLabeler` on the same chat, compute Cohen's κ per
label. Surfaces taxonomy ambiguity.

### v0.4 — Cross-chat backlink resolution
Detect topic overlap between artifacts across chats and emit Obsidian
`[[...]]` backlinks. Use FTS5 + embedding similarity (sentence-transformers
optional dependency).

### v0.5 — MIDAS migration path
Add `gitllm relabel --taxonomy midas` to re-tag every turn using the
`midas_hint` column. Validates ADR-002.

### v0.6 — Real-time labeling
A small daemon that watches a chat-export folder (Claude/ChatGPT exports)
and auto-ingests + labels.
