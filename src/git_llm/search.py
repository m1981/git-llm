"""Query interface: combine label filters with FTS5 full-text search."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(slots=True)
class SearchHit:
    chat_id: int
    chat_title: str
    turn_idx: int
    role: str
    snippet: str
    labels: list[str]


def search(
    conn: sqlite3.Connection,
    *,
    label: str | None = None,
    master_class: str | None = None,
    text: str | None = None,
    chat_id: int | None = None,
    limit: int = 20,
) -> list[SearchHit]:
    """
    Search across all chats.

    - `label`        : filter turns carrying this label.
    - `master_class` : filter by Austin master class.
    - `text`         : FTS5 MATCH query (e.g. "sqlalchemy AND pool").
    - `chat_id`      : restrict to a single chat.
    """
    where: list[str] = []
    params: list[object] = []
    join_fts = ""

    if text:
        join_fts = "JOIN turns_fts f ON f.rowid = t.id"
        where.append("f.content MATCH ?")
        params.append(text)
    if label:
        where.append("EXISTS (SELECT 1 FROM labels l WHERE l.turn_id = t.id AND l.name = ?)")
        params.append(label)
    if master_class:
        where.append(
            "EXISTS (SELECT 1 FROM labels l WHERE l.turn_id = t.id AND l.master_class = ?)"
        )
        params.append(master_class)
    if chat_id is not None:
        where.append("t.chat_id = ?")
        params.append(chat_id)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT t.id AS turn_id, t.chat_id, t.idx, t.role,
               substr(t.content, 1, 280) AS snippet,
               c.title AS chat_title,
               COALESCE(GROUP_CONCAT(DISTINCT l2.name), '') AS labels
        FROM turns t
        JOIN chats c ON c.id = t.chat_id
        {join_fts}
        LEFT JOIN labels l2 ON l2.turn_id = t.id
        {where_sql}
        GROUP BY t.id
        ORDER BY t.chat_id, t.idx
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [
        SearchHit(
            chat_id=r["chat_id"],
            chat_title=r["chat_title"],
            turn_idx=r["idx"],
            role=r["role"],
            snippet=r["snippet"],
            labels=[x for x in (r["labels"] or "").split(",") if x],
        )
        for r in rows
    ]
