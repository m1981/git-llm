#!/usr/bin/env python3
"""Generate search-index.json from the gallery SQLite DB.

Usage:
    python scripts/gen_search_index.py gallery/gallery.sqlite --out gallery/search-index.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def generate(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Chat metadata
    chats = {}
    for r in conn.execute("SELECT id, title, session_id, source FROM chats"):
        chats[r["id"]] = {
            "title": r["title"],
            "session_id": r["session_id"] or "",
            "source": r["source"],
        }

    # Turns with labels
    rows = conn.execute("""
        SELECT t.chat_id, t.idx, t.role, t.content, t.token_estimate,
               GROUP_CONCAT(DISTINCT l.name) AS labels
        FROM turns t
        LEFT JOIN labels l ON l.turn_id = t.id
        GROUP BY t.id
        ORDER BY t.chat_id, t.idx
    """).fetchall()

    turns = []
    for r in rows:
        chat = chats.get(r["chat_id"], {})
        content = r["content"]
        turns.append({
            "chat_id": r["chat_id"],
            "chat_title": chat.get("title", "?"),
            "session_id": chat.get("session_id", "")[:12],
            "idx": r["idx"],
            "role": r["role"],
            "snippet": content[:300].replace("\n", " ").strip(),
            "content": content,
            "labels": [l for l in (r["labels"] or "").split(",") if l],
            "char_count": len(content),
        })

    conn.close()

    return {
        "chats": chats,
        "turns": turns,
        "meta": {
            "total_chats": len(chats),
            "total_turns": len(turns),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", help="Path to gallery.sqlite")
    parser.add_argument("--out", default="gallery/search-index.json")
    args = parser.parse_args()

    data = generate(args.db_path)
    out = Path(args.out)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"✓ {out} ({data['meta']['total_turns']} turns, {out.stat().st_size // 1024}K)")


if __name__ == "__main__":
    main()
