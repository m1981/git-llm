# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Black-box evaluation kit** (`docs/evaluation/`). Seven-scenario protocol
  that dogfoods on real pi.dev sessions: ingestion, labeling, phase compression,
  search recall, extraction precision/recall, cross-chat, and the meta-test
  (self-recognition). Single rubric drives both human (`scorecard.md`) and AI
  (`scorecard.schema.json`) evaluation surfaces. Run with
  `bash docs/evaluation/run.sh`.

- **Evaluation gold data** (`docs/evaluation/gold/`). Versioned gold files:
  - `session-2-prompts.yaml` — 11 verified user prompts with provisional labels.
  - `expected-phases.yaml` — 6-phase narrative arc with boundary expectations.
  - `expected-artifacts.yaml` — 6 gold knowledge notes + ADRs, plus anti-gold
    entries for false-positive detection.
  - `search-queries.yaml` — 10 natural-language queries with expected answer turns.

- **`--role` option on `gitllm label`**. Label only user or assistant turns
  instead of every turn. Dramatically reduces LLM API cost and time
  (e.g. 12 user turns vs. 121 total).
  ```bash
  gitllm label 2 --model claude-sonnet-4-5 --role user
  ```

- **Value proposition document** (`docs/value-proposition.md`). Captures user
  goals (functional, emotional, social), explains each theoretical framework
  (Austin, SwDA/MIDAS, Zettelkasten, NLP, ADRs) for non-technical readers,
  and maps the value chain from raw chat to permanent knowledge bank.

- **LLM labeler smoke test** (`scripts/test_llm_labeler.sh`). Standalone
  script that creates a throwaway DB, ingests a 2-turn sample chat, labels
  it with the configured LLM, and prints the results. Validates API key,
  model connectivity, and JSON response parsing in one command.

- **Environment template** (`.env`). Documents `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, and `GITLLM_LABEL_MODEL` with comments. `.env` and
  `scripts/.env` are now in `.gitignore` to prevent accidental key commits.

- **FTS5 special-character quoting** (`docs/evaluation/run.sh`). Inline
  `_fts_quote()` helper wraps queries containing `-`, `:`, `*` in double
  quotes so FTS5 doesn't parse them as operators (e.g. `pi-session-export`
  no longer triggers `no such column: session`).

- **Backlink resolution** (`src/git_llm/extract.py`). Extracted zettels now
  get bidirectional `related:` links when they share ≥2 labels. Links are
  persisted to the existing `artifact_links` table (previously unused) and
  written to YAML frontmatter. Fully connected graph with 100% precision
  and recall on the dogfood corpus.

- **Inter-labeler agreement** (`scripts/eval_kappa.py`). Computes Cohen's κ
  between any two labelers (stub, LLM, human gold) on the same turns.
  Reports primary κ, master-class κ, exact match rate, and label bias.
  Current result: κ(stub, LLM) = 0.271 (fair).

- **Cross-chat clustering** (`scripts/eval_clusters.py`). Groups zettels
  from multiple chats by label Jaccard similarity (agglomerative clustering).
  Reports cluster count, cross-chat ratio, coherence, and singleton rate.
  Current result: 4 clusters, 2 cross-chat, coherence 0.267.

- **Session scanner** (`scripts/scan_sessions.py`). Scans all pi.dev sessions
  and ranks by meta-test suitability. Scores pivots, challenges, decisions,
  educational content, questions, code sharing, and session length. Found
  119 sessions with ≥1 user prompt across 44 repos.

- **Session viewer** (`docs/evaluation/session-view.html`). Interactive HTML
  viewer for labeled sessions. Features: phase timeline navigation, turn
  cards with label badges, content search with highlighting, thinking/tool
  toggle, extracted artifact links. Zero dependencies — single HTML file
  that reads a JSON data file. Generator: `scripts/gen_session_view.py`.

- **Evaluation report** (`docs/evaluation/REPORT.md`). Full written report
  covering all 7 evaluation dimensions with data tables, phase maps, label
  distributions, bug catalog, and v0.2 recommendations. Composite score:
  0.84 — Green for personal use.

- **Evaluation specs for roadmap features** (`docs/evaluation/SPEC-unimplemented.md`).
  Detailed designs for inter-labeler agreement, backlink resolution, and
  cross-chat clustering — each with rubric criteria, gold data format,
  runnable test, and implementation plan.

- **Architecture overview** (`docs/architecture.md`, section 2). Names the
  12 design patterns used throughout the codebase (Value Objects, Repository
  + Unit of Work, Adapter, Strategy, Specification, Pipeline, Bidirectional
  Link, Additive Migration, Idempotency Key, Two-Pass Merge, Single Source
  of Truth, Facade). Includes an ASCII component map and five deliberate
  non-decisions.

- **5 Mermaid sequence diagrams** (`docs/architecture.md`, section 3).
  Covers the five dominant runtime flows:
  - 3.1 Bulk pi-session import (idempotent, dedup on `session_id`)
  - 3.2 Labeling with role filter (stub vs LLM, JSON-fence stripping)
  - 3.3 Phase compression (user-prompt grouping + two-pass Jaccard merge)
  - 3.4 Knowledge extraction with backlink resolution (4-stage pipeline)
  - 3.5 Search (incremental FTS5 + label + master-class filter builder)

- **ADR-011: Bidirectional backlinks via label overlap**. Pairs sharing
  ≥2 labels get bidirectional links; persisted to the previously unused
  `artifact_links` table. 42 links on dogfood corpus, 100% precision.

- **ADR-012: Thinking-block extraction needs a strong-trigger gate**.
  Thinking blocks promoted only if labeled `Synthesizing`, `Pragmatic+Warning`,
  or `Reflective`. Documents the 38% → 100% precision improvement and the
  thinking-block recall challenge on tool-heavy sessions.

- **ADR-013: Phase compression groups by user prompt, not raw turn**.
  User-prompt grouping + two-pass merge (Jaccard 0.1 pass + force-merge cap
  at 8). Documents the 22→7 phase reduction and the topic-pivot blind spot.

### Changed

- **Phase compression algorithm** (`src/git_llm/phases.py`). Completely rewritten.
  Now groups turns by user prompt (not raw turn), derives each group's phase
  from the dominant Austin master class, and merges consecutive same-state
  phases in two passes (Jaccard threshold + force-merge cap at 8). Result:
  22 phases → 5–7 on a 250-turn chat. Flow display deduplicates consecutive
  identical master classes.

- **Knowledge extraction triggers** (`src/git_llm/taxonomy.py`). Added
  `("Synthesizing",)` as a standalone knowledge trigger. In LLM-labeled
  sessions, `Synthesizing` is a high-signal label that marks thinking blocks
  where the model integrates multiple concepts into coherent conclusions.

- **Thinking block extraction policy** (`src/git_llm/extract.py`).
  `_is_knowledge_worthy()` is now label-aware: thinking blocks are promoted
  to knowledge notes only if labeled with `Synthesizing`, `Pragmatic+Warning`,
  or `Reflective`. This captures genuinely valuable reasoning (architectural
  analysis, design synthesis) while filtering out raw reasoning traces.

- **`label_chat()` signature** (`src/git_llm/label.py`). Now accepts an
  optional `role: str | None` parameter. When set, only turns matching that
  role are labeled. Existing callers with `role=None` are unaffected.

- **Evaluation run.sh** now sources `.env` / `scripts/.env` for API keys,
  uses `--role user` for the LLM labeler pass, defaults to
  `claude-sonnet-4-5` as the LLM model, and queries SQLite directly for
  structured JSON output (the CLI's `search` command doesn't have a
  `--json` flag).

- **`docs/evaluation/run.sh`** resolved by `chat_id` by querying the chat
  with the most user turns, rather than parsing CLI JSON output that
  doesn't exist.

- **Architecture documentation** (`docs/architecture.md`). Updated data model
  to note `artifact_links` is now wired (ADR-011). Module dependency rules
  expanded with off-pipeline tools (`scripts/eval_kappa.py`, `eval_backlinks.py`,
  `eval_clusters.py`, `scan_sessions.py`, `gen_session_view.py`). Test count
  corrected from 104 to 66. Pipeline summary extended with evaluation commands.
  Roadmap updated: v0.3 (inter-labeler agreement) marked done, v0.4 (cross-chat
  backlinks) marked partial.

### Fixed

- **Pi session import crash on embedded `\r`** (`src/git_llm/pi_import.py`).
  Changed `text.splitlines()` to `text.split("\n")` — `splitlines()` splits on
  `\r` characters embedded inside JSON string values, breaking the parser on
  sessions where content contains literal carriage returns.

- **Extraction precision** (`src/git_llm/extract.py`). Added `_is_knowledge_worthy()`
  content filter: turns starting with `[thinking]` are now skipped entirely,
  and turns with <200 chars of real content (after stripping thinking blocks
  and `[tool_use:...]` markers) are not promoted to knowledge notes.
  Precision: 38% → 100% on the dogfood corpus (21 zettels → 6, all genuine).

- **LLMLabeler JSON parsing** (`src/git_llm/label.py`). Claude models wrap
  responses in ` ```json ``` ` markdown fences, causing `json.loads()` to
  fail silently and return zero labels. The parser now strips opening and
  closing code fences before attempting to parse.

- **Evaluation run.sh previously failed** with `gitllm: command not found`
  because the venv wasn't activated in the subshell. Now sources
  `.venv/bin/activate` and validates `gitllm` is on PATH before proceeding.

- **Evaluation run.sh previously used `--json` flag** on `gitllm search`
  (doesn't exist) and `--labeler` flag on `gitllm label` (correct flag
  is `--model`). All invocations now use the actual CLI interface.

- **Zettel file discovery** in evaluation. Zettels are written to
  `zettel/notes/` (nested), not `zettel/` directly. All listing and
  grepping now uses `find ... -name '*.md'` instead of `ls`.

- **Model ID** for Anthropic. Changed default from `claude-sonnet-4-20250514`
  (returns 404 on current API) to `claude-sonnet-4-5` (latest available).
  Model is overridable via `GITLLM_LABEL_MODEL` environment variable.
