"""
Ingest chat exports into the DB.

Format precedence (most robust first):
    1. JSONL — one TurnExport per line. Canonical source format.
       Auto-detects pi.dev agent sessions (heterogeneous line types) and
       routes them through `pi_import.parse_pi_session` losslessly.
    2. JSON  — either a bare array of turns or an envelope
               ({"messages": [...]} / {"turns": [...]} / {"conversation": [...]}).
    3. Markdown — best-effort: `# user` / `# AI` / `# assistant` headings.
                  Code fences are skipped so they cannot create false boundaries.

The markdown path is intentionally lossy and is provided only for copy-paste
convenience. For production use, prefer JSONL (see `gitllm convert`).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from git_llm.models import Chat, Turn
from git_llm.pi_import import is_pi_session, parse_pi_session
from git_llm.schema import ChatExport, TurnExport
from git_llm.taxonomy import Role


# ---------------------------------------------------------------------------
# Markdown parser (hardened: code-fence aware, strict heading match)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,3})\s+(user|ai|assistant|model)\s*$", re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")


def _normalize_role(raw: str) -> Role:
    return Role.USER if raw.lower() == "user" else Role.ASSISTANT


def parse_markdown(text: str, *, strict: bool = False) -> list[tuple[Role, str]]:
    """
    Split a markdown chat dump into ordered (role, content) tuples.

    - Headings inside fenced code blocks are ignored.
    - With `strict=True`, raises if no headings are found.
    """
    turns: list[tuple[Role, str]] = []
    current_role: Role | None = None
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        if current_role is not None and buffer:
            content = "\n".join(buffer).strip()
            if content:
                turns.append((current_role, content))

    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue
        if not in_fence:
            m = _HEADING_RE.match(line)
            if m:
                flush()
                current_role = _normalize_role(m.group(2))
                buffer = []
                continue
        buffer.append(line)
    flush()

    if strict and not turns:
        raise ValueError(
            "No `# user` / `# AI` headings found. Use JSONL for unambiguous ingestion."
        )
    return turns


# ---------------------------------------------------------------------------
# JSON / JSONL parsers (canonical)
# ---------------------------------------------------------------------------

_ENVELOPE_KEYS = ("messages", "turns", "conversation")


def parse_json(text: str) -> tuple[ChatExport, list[tuple[Role, str]]]:
    data = json.loads(text)

    if isinstance(data, list):
        export = ChatExport(messages=[TurnExport.model_validate(d) for d in data])
    elif isinstance(data, dict):
        messages_raw = next((data[k] for k in _ENVELOPE_KEYS if k in data), None)
        if messages_raw is None:
            raise ValueError(f"JSON envelope must contain one of {_ENVELOPE_KEYS!r}.")
        export = ChatExport(
            title=data.get("title"),
            model=data.get("model"),
            messages=[TurnExport.model_validate(d) for d in messages_raw],
            metadata={k: v for k, v in data.items() if k not in {*_ENVELOPE_KEYS, "title", "model"}},
        )
    else:
        raise ValueError("JSON root must be a list or an object envelope.")

    return export, _flatten(export)


def parse_jsonl(text: str) -> tuple[ChatExport, list[tuple[Role, str]]]:
    """One TurnExport per non-empty line — OR a pi session (auto-detected)."""
    first_line = next((l for l in text.splitlines() if l.strip()), "")
    if is_pi_session(first_line):
        export = parse_pi_session(text)
        return export, _flatten(export)

    turns_export: list[TurnExport] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            turns_export.append(TurnExport.model_validate_json(line))
        except ValidationError as e:
            raise ValueError(f"JSONL line {lineno} invalid: {e}") from e
    export = ChatExport(messages=turns_export)
    return export, _flatten(export)


def _flatten(export: ChatExport) -> list[tuple[Role, str]]:
    """Drop system messages, normalize role, flatten content blocks."""
    out: list[tuple[Role, str]] = []
    for msg in export.messages:
        if msg.role == "system":
            continue
        text = msg.to_text()
        if text:
            out.append((Role(msg.role), text))
    return out


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def parse_file(path: Path) -> tuple[ChatExport | None, list[tuple[Role, str]]]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        return parse_jsonl(text)
    if suffix == ".json":
        return parse_json(text)
    return None, parse_markdown(text)


# ---------------------------------------------------------------------------
# DB writes
# ---------------------------------------------------------------------------

def ingest_file(
    conn: sqlite3.Connection,
    path: Path,
    title: str | None = None,
    *,
    skip_if_exists: bool = False,
) -> int:
    """
    Insert chat + turns. Returns the new (or existing) chat_id.

    When the export carries a `session_id` in its metadata (pi.dev sessions do),
    that value is the dedup key. With `skip_if_exists=True` a duplicate session
    is a no-op that returns the existing chat_id. With `skip_if_exists=False`
    a duplicate raises ValueError so users notice accidental re-imports.
    """
    export, turns_raw = parse_file(path)
    if not turns_raw:
        raise ValueError(f"No turns parsed from {path}")

    session_id = export.metadata.get("session_id") if export else None
    if session_id:
        row = conn.execute(
            "SELECT id FROM chats WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row:
            if skip_if_exists:
                return int(row["id"])
            raise ValueError(
                f"Session {session_id} already ingested as chat_id={row['id']}. "
                f"Pass skip_if_exists=True to make this a no-op."
            )

    chat = Chat(
        title=title or (export.title if export else None) or path.stem,
        source=path.suffix.lstrip(".") or "md",
        created_at=(export.created_at if export and export.created_at else datetime.utcnow()),
        raw_path=str(path.resolve()),
        session_id=session_id,
    )
    cur = conn.execute(
        "INSERT INTO chats (title, source, created_at, raw_path, session_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (chat.title, chat.source, chat.created_at.isoformat(), chat.raw_path, chat.session_id),
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
    return max(1, len(text) // 4)


def fetch_turns(conn: sqlite3.Connection, chat_id: int) -> list[Turn]:
    rows = conn.execute(
        "SELECT id, chat_id, idx, role, content, token_estimate "
        "FROM turns WHERE chat_id = ? ORDER BY idx",
        (chat_id,),
    ).fetchall()
    return [Turn(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Conversion (md → jsonl)
# ---------------------------------------------------------------------------

def md_to_jsonl(md_text: str) -> str:
    """Render a markdown chat dump as canonical JSONL."""
    turns = parse_markdown(md_text, strict=True)
    lines = [
        TurnExport(role=role.value, content=content).model_dump_json(exclude_none=True)
        for role, content in turns
    ]
    return "\n".join(lines) + "\n"
