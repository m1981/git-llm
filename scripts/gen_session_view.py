#!/usr/bin/env python3
"""Generate session-view.json for the HTML session viewer.

Usage:
    python scripts/gen_session_view.py <db_path> <chat_id> [--out session-view.json]

Reads a labeled chat from the git-llm SQLite database and produces a JSON
file consumed by docs/evaluation/session-view.html.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from git_llm.phases import compute_phases


_THINKING_RE = re.compile(r"^\[thinking]\s*\n", re.IGNORECASE)
_TOOL_USE_RE = re.compile(r"^\[tool_use:\w+]")


def _classify_content(content: str) -> str:
    """Return 'thinking', 'tool', or 'text'."""
    s = content.strip()
    if _THINKING_RE.match(s):
        return "thinking"
    if _TOOL_USE_RE.match(s) and len(s) < 200:
        return "tool"
    return "text"


def generate(db_path: str, chat_id: int) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # ── Metadata ─────────────────────────────────────────────────────────
    chat = conn.execute(
        "SELECT id, title, source, created_at, session_id FROM chats WHERE id = ?",
        (chat_id,),
    ).fetchone()
    if not chat:
        raise ValueError(f"Chat {chat_id} not found in {db_path}")

    turn_count = conn.execute(
        "SELECT COUNT(*) AS n FROM turns WHERE chat_id = ?", (chat_id,)
    ).fetchone()["n"]
    label_count = conn.execute(
        "SELECT COUNT(*) AS n FROM labels l JOIN turns t ON t.id = l.turn_id WHERE t.chat_id = ?",
        (chat_id,),
    ).fetchone()["n"]

    # ── Phases ───────────────────────────────────────────────────────────
    phases = compute_phases(conn, chat_id)
    phases_data = []
    for p in phases:
        phases_data.append({
            "start": p.turn_start,
            "end": p.turn_end,
            "state": p.state,
            "flow": [mc.value for mc in p.flow],
            "labels": list(p.dominant_labels),
        })

    # ── Turns ────────────────────────────────────────────────────────────
    rows = conn.execute(
        """
        SELECT t.id, t.idx, t.role, t.content, t.parent_id,
               GROUP_CONCAT(DISTINCT l.name) AS labels
        FROM turns t
        LEFT JOIN labels l ON l.turn_id = t.id
        WHERE t.chat_id = ?
        GROUP BY t.id
        ORDER BY t.idx
        """,
        (chat_id,),
    ).fetchall()

    turns_data = []
    for r in rows:
        content = r["content"]
        turns_data.append({
            "idx": r["idx"],
            "role": r["role"],
            "content": content,
            "content_type": _classify_content(content),
            "char_count": len(content),
            "labels": [l for l in (r["labels"] or "").split(",") if l],
        })

    # ── Extracted artifacts ──────────────────────────────────────────────
    artifacts_data = []
    try:
        arts = conn.execute(
            "SELECT kind, title, zk_id, turn_start, turn_end, labels, file_path FROM artifacts WHERE chat_id = ?",
            (chat_id,),
        ).fetchall()
        for a in arts:
            artifacts_data.append({
                "kind": a["kind"],
                "title": a["title"],
                "id": a["zk_id"],
                "turn_start": a["turn_start"],
                "turn_end": a["turn_end"],
                "labels": a["labels"].split(",") if a["labels"] else [],
            })
    except Exception:
        pass  # artifacts table may not exist yet

    conn.close()

    return {
        "meta": {
            "chat_id": chat["id"],
            "title": chat["title"],
            "source": chat["source"],
            "session_id": chat["session_id"],
            "created_at": chat["created_at"],
            "turn_count": turn_count,
            "label_count": label_count,
        },
        "phases": phases_data,
        "turns": turns_data,
        "artifacts": artifacts_data,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate session-view.json")
    parser.add_argument("db_path", help="Path to git-llm SQLite database")
    parser.add_argument("chat_id", type=int, help="Chat ID to export")
    parser.add_argument("--out", default="session-view.json", help="Output JSON path")
    parser.add_argument("--embed", action="store_true", help="Create self-contained HTML with embedded data")
    args = parser.parse_args()

    data = generate(args.db_path, args.chat_id)
    out = Path(args.out)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Wrote {out} ({len(data['turns'])} turns, {len(data['phases'])} phases, {len(data['artifacts'])} artifacts)")

    if args.embed:
        html_template = Path(__file__).parent.parent / "docs" / "evaluation" / "session-view.html"
        if not html_template.exists():
            html_template = Path("docs/evaluation/session-view.html")
        html = html_template.read_text(encoding="utf-8")
        json_str = json.dumps(data, ensure_ascii=False)
        # Inject <script id="session-data" type="application/json"> before </body>
        embed_tag = f'<script id="session-data" type="application/json">{json_str}</script>'
        html = html.replace("</body>", f"{embed_tag}\n</body>")
        # Write to a separate file to avoid overwriting the template
        embed_path = out.parent / f"{out.stem}-embedded.html"
        embed_path.write_text(html, encoding="utf-8")
        print(f"✓ Embedded into {embed_path} ({embed_path.stat().st_size // 1024}K)")


if __name__ == "__main__":
    main()
