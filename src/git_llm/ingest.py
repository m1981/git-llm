"""
Ingest chat exports into the DB.

Supported formats:
    - Markdown with `# user` / `# AI` (or `# assistant`) headings between turns.
      This matches `docs/initial-conversation.md` and is the lingua franca for
      copy-pasted chats.
    - JSON: a list of {"role": "user|assistant", "content": "..."} objects.

The parser is deliberately tolerant: leading/trailing whitespace, mixed-case
role headings, and empty turns are normalized.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from git_llm.models import Chat, Turn
from git_llm.taxonomy import Role

# Match a heading line of form `# user`, `## AI`, `# assistant`, case-insensitive.
_HEADING_RE = re.compile(r"^\s{0,3}#{1,3}\s+(user|ai|assistant|model)\s*$", re.IGNORECASE)


def _normalize_role(raw: str) -> Role:
    raw = raw.lower()
    if raw == "user":
        return Role.USER
    return Role.ASSISTANT  # ai | assistant | model


def parse_markdown(text: str) -> list[tuple[Role, str]]:
    """Split a markdown chat dump into ordered (role, content) tuples."""
    turns: list[tuple[Role, str]] = []
    current_role: Role | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current_role is not None and buffer:
            content = "\n".join(buffer).strip()
            if content:
                turns.append((current_role, content))

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            current_role = _normalize_role(m.group(1))
            buffer = []
        else:
            buffer.append(line)
    flush()
    return turns


def parse_json(text: str) -> list[tuple[Role, str]]:
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("JSON chat export must be a list of turn objects.")
    out: list[tuple[Role, str]] = []
    for entry in data:
        role = _normalize_role(str(entry["role"]))
        content = str(entry["content"]).strip()
        if content:
            out.append((role, content))
    return out


def parse_file(path: Path) -> list[tuple[Role, str]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return parse_json(text)
    return parse_markdown(text)


def ingest_file(conn: sqlite3.Connection, path: Path, title: str | None = None) -> int:
    """Insert chat + turns. Returns the new chat_id."""
    turns_raw = parse_file(path)
    if not turns_raw:
        raise ValueError(f"No turns parsed from {path}")

    chat = Chat(
        title=title or path.stem,
        source=path.suffix.lstrip(".") or "md",
        created_at=datetime.utcnow(),
        raw_path=str(path.resolve()),
    )
    cur = conn.execute(
        "INSERT INTO chats (title, source, created_at, raw_path) VALUES (?, ?, ?, ?)",
        (chat.title, chat.source, chat.created_at.isoformat(), chat.raw_path),
    )
    chat_id = int(cur.lastrowid)

    rows = [
        (chat_id, idx, role.value, content, _estimate_tokens(content))
        for idx, (role, content) in enumerate(turns_raw)
    ]
    conn.executemany(
        "INSERT INTO turns (chat_id, idx, role, content, token_estimate) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return chat_id


def _estimate_tokens(text: str) -> int:
    """Cheap heuristic: ~4 chars per token. Good enough for budgeting."""
    return max(1, len(text) // 4)


def fetch_turns(conn: sqlite3.Connection, chat_id: int) -> list[Turn]:
    rows = conn.execute(
        "SELECT id, chat_id, idx, role, content, token_estimate "
        "FROM turns WHERE chat_id = ? ORDER BY idx",
        (chat_id,),
    ).fetchall()
    return [Turn(**dict(r)) for r in rows]
