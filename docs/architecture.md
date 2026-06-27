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

### ADR-007: Adopt pi-session lessons via additive schema, not full mirror
- **Status:** Accepted
- **Context:** The `pi-session-export` skill stores agent sessions as JSONL
  with a richer shape than ours: per-line `type` envelope, DAG via
  `parentId`, first-class `thinking` blocks, per-turn `usage` + cost,
  mid-session control events (`model_change`, `thinking_level_change`).
- **Decision:** Adopt the *capabilities* that improve labeling and
  extraction; reject the structural choices that are agent-runtime-specific.
  Specifically:
  - **Adopted (additive to `TurnExport`):**
    - `parent_id: str | None` — DAG edge; enables branch analysis without
      forcing a tree on linear chats.
    - `usage: UsageInfo | None` — input/output/cache tokens + cost.
    - `ContentBlock(type="thinking", thinking=str)` — reasoning traces
      are first-class, FTS-indexed, and surfaced with a `[thinking]`
      marker in `to_text()` so the labeler can distinguish them.
  - **Rejected:**
    - Heterogeneous line-type envelope (`type` field per line). Pi needs
      this because it logs a live agent. We capture finished conversations
      — one schema per line keeps JSONL grep/diff/validation simple.
    - camelCase keys (`toolCall`, `cacheRead`). We follow OpenAI/Anthropic
      snake_case so provider logs ingest unmodified.
  - **Translated, not adopted:**
    - `model_change` / `thinking_level_change` → buffered and attached to
      the *next* message as `metadata.control_events`.
    - `api`, `provider`, `stopReason`, `responseId` → `metadata`.
- **Consequences:** A new `pi_import.parse_pi_session()` adapter performs
  lossless translation. Pi sessions auto-detect in `parse_jsonl` (header
  line is `{"type":"session",...}`). Our canonical JSONL remains
  provider-agnostic and one-schema-per-line.

### ADR-006: JSONL is canonical; markdown is best-effort
- **Status:** Accepted (revises v0.1)
- **Context:** Markdown headings (`# user` / `# AI`) as turn boundaries are fragile:
  collisions inside code fences, no metadata, no multimodal, no edit history.
  Every real chat-export tool (OpenAI API, Anthropic API, ChatGPT export,
  Claude export) already produces JSON.
- **Decision:** Make **JSONL** (one `TurnExport` per line) the canonical source
  format. Accept JSON envelopes (`{messages: [...]}`) for direct provider
  compatibility. Keep markdown ingestion but harden it (skip code fences,
  require exact heading match) and ship `gitllm convert` to migrate users
  off markdown.
- **Schema:** mirrors the OpenAI/Anthropic `messages` shape — `role`,
  `content` (str or list of `ContentBlock`), plus optional `timestamp`,
  `model`, `id`, `metadata`. System messages are dropped at ingest;
  non-text blocks (`image`, `tool_use`, `tool_result`) are preserved as
  text markers so turn count and ordering are stable.
- **Consequences:** Round-trip safe with provider APIs. JSONL is
  append-only friendly, streamable, and diff-friendly. Markdown remains
  available for copy-paste but emits a clear migration command.

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

### v0.2 — Provider-specific importers
Native readers for ChatGPT and Claude export zips, which encode
conversations as message *trees* (re-generated branches) rather than
linear lists. Linearize by walking the chosen branch.

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
