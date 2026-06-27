# git-llm

> Capture, label, search, and extract knowledge from LLM chat histories using dialogue-act tagging.

`git-llm` treats your LLM conversations like a versioned codebase. Each turn is
labeled with a **dialogue act** (Inquiring, Pivoting, Pragmatic, Warning, …),
stored in a queryable SQLite database with full-text search, and distilled into
atomic Zettelkasten notes for your permanent knowledge base.

## Why

Heavy LLM users hit four pains:

1. **Recall** — *"In which of my 50 chats did we discuss connection pooling?"*
2. **Navigation** — *"Where in this 40-turn chat was the architectural decision?"*
3. **Signal vs. noise** — *"Which turns are dead branches I should ignore?"*
4. **Knowledge extraction** — *"How do I get the gold out of the chat and into Obsidian?"*

`git-llm` solves all four with one pipeline: **ingest → label → store → search → extract**.

## Install

```bash
git clone <this-repo> git-llm && cd git-llm
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Quickstart

```bash
# 1. Initialize the database (default: ~/.git-llm/chatdb.sqlite)
gitllm init

# 2. Ingest a markdown chat export (# user / # AI headings between turns)
gitllm ingest docs/initial-conversation.md --title "Initial Conversation"

# 3. Label every turn (offline heuristic — no API key needed)
gitllm label 1

#    …or use a real LLM via LiteLLM (any provider):
gitllm label 1 --model gpt-4o-mini

# 4. See the macro-phase map of the chat
gitllm phases 1

# 5. Search across all chats
gitllm search --text "sqlalchemy AND pool"
gitllm search --label Warning
gitllm search --class Verdictive --text reflex

# 6. Extract Zettelkasten notes + ADRs into Obsidian-compatible markdown
gitllm extract 1 --out ./zettel
```

## How it works

```
┌──────────┐  parse  ┌──────────┐  classify  ┌──────────┐  trigger  ┌──────────┐
│ chat .md │ ──────▶ │  turns   │ ─────────▶ │  labels  │ ────────▶ │ zettels  │
└──────────┘         └──────────┘            └──────────┘           └──────────┘
                          │                       │                       │
                          ▼                       ▼                       ▼
                       FTS5                Austin master            Obsidian-
                       index               classes + MIDAS          compatible
                                           hints                    .md files
```

- **Taxonomy**: the user's 20 labels (10 user + 10 assistant), grouped under
  Austin's 5 master classes (Expositive, Exercitive, Verdictive, Commissive,
  Behabitive). MIDAS hints are stored for future migration to a research-grade
  taxonomy. See [`src/git_llm/taxonomy.py`](src/git_llm/taxonomy.py).
- **Labeler**: pluggable. Ships with `StubLabeler` (regex heuristics, offline)
  and `LLMLabeler` (LiteLLM → any provider).
- **Storage**: SQLite with FTS5 full-text index. Single-file, zero ops.
- **Extraction**: rule-based triggers map label patterns to artifact kinds:
  - `[Educational]`, `[Reflective]`, `[Pragmatic+Warning]` → **knowledge note**
  - `[Pivoting/Challenging] → [Pragmatic/Analytical] → [Synthesizing/Structuring]` → **ADR**

## Project layout

```
src/git_llm/
  taxonomy.py    20 labels + Austin classes + MIDAS hints
  models.py      Pydantic domain models
  db.py          SQLite schema + FTS5
  ingest.py      Markdown / JSON parsers
  label.py       StubLabeler + LLMLabeler (LiteLLM)
  phases.py      Adjacency-pair → macro-phase compression
  extract.py     Trigger rules → Zettelkasten markdown
  search.py      Combined label + FTS5 queries
  cli.py         Typer CLI (`gitllm <command>`)
tests/           pytest, dogfoods docs/initial-conversation.md
docs/
  architecture.md   Design rationale + ADR-style decisions
```

## Tests

```bash
pytest
```

The test suite uses your real `docs/initial-conversation.md` as a fixture —
the system dogfoods on the conversation that inspired it.

## Roadmap

See [`docs/architecture.md`](docs/architecture.md) for design decisions and
the next planned features (Infelicity Report, inter-labeler agreement,
backlink resolution, cross-chat clustering).

## License

MIT
