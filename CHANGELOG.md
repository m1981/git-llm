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

### Changed

- **Phase compression algorithm** (`src/git_llm/phases.py`). Completely rewritten.
  Now groups turns by user prompt (not raw turn), derives each group's phase
  from the dominant Austin master class, and merges consecutive same-state
  phases in two passes (Jaccard threshold + force-merge cap at 8). Result:
  22 phases → 5–7 on a 250-turn chat. Flow display deduplicates consecutive
  identical master classes.

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

### Fixed

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
