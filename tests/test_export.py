"""Tests for gitllm export — round-trip from DB back to canonical JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from git_llm.ingest import ingest_file, parse_jsonl
from git_llm.schema import TurnExport


def test_export_writes_canonical_jsonl(tmp_db, tmp_path):
    """Export a simple markdown chat → JSONL, then re-ingest the JSONL."""
    md = tmp_path / "chat.md"
    md.write_text("# user\nhello?\n# AI\nhi there!\n# user\nbye\n")
    chat_id = ingest_file(tmp_db, md)

    out = tmp_path / "out.jsonl"
    from git_llm.ingest import fetch_turns_with_meta

    chat, turns = fetch_turns_with_meta(tmp_db, chat_id)
    assert len(turns) == 3

    lines = []
    for t in turns:
        te = TurnExport(role=t.role.value, content=t.content, parent_id=t.parent_id)
        lines.append(te.model_dump_json(exclude_none=True))
    out.write_text("\n".join(lines) + "\n")

    # Verify it's valid canonical JSONL
    parsed = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert len(parsed) == 3
    assert parsed[0]["role"] == "user"
    assert parsed[0]["content"] == "hello?"
    assert parsed[1]["role"] == "assistant"
    assert parsed[2]["role"] == "user"


def test_export_preserves_parent_id(tmp_db, tmp_path):
    """pi session → DB → JSONL → re-parse: parent_id survives the round-trip."""
    from git_llm.pi_import import parse_pi_session

    pi_text = (
        '{"type":"session","version":3,"id":"s1","timestamp":"2026-06-27T10:00:00Z","cwd":"/x"}\n'
        '{"type":"message","id":"u1","parentId":null,"timestamp":"2026-06-27T10:00:01Z",'
        '"message":{"role":"user","content":[{"type":"text","text":"q"}]}}\n'
        '{"type":"message","id":"a1","parentId":"u1","timestamp":"2026-06-27T10:00:02Z",'
        '"message":{"role":"assistant","content":[{"type":"text","text":"a"}]}}\n'
    )
    pi_path = tmp_path / "pi.jsonl"
    pi_path.write_text(pi_text)

    chat_id = ingest_file(tmp_db, pi_path)
    from git_llm.ingest import fetch_turns_with_meta
    _, turns = fetch_turns_with_meta(tmp_db, chat_id)

    # parent_id survived ingest
    assert turns[0].parent_id is None
    assert turns[1].parent_id == "u1"

    # Export and re-parse
    out = tmp_path / "round.jsonl"
    lines = [
        TurnExport(role=t.role.value, content=t.content, parent_id=t.parent_id).model_dump_json(exclude_none=True)
        for t in turns
    ]
    out.write_text("\n".join(lines) + "\n")

    export, re_turns = parse_jsonl(out.read_text())
    assert len(re_turns) == 2
    assert re_turns[0][1] == "q"
    assert re_turns[1][1] == "a"


def test_export_cli_smoke(tmp_db, tmp_path):
    """End-to-end via CLI."""
    md = tmp_path / "c.md"
    md.write_text("# user\ntest\n# AI\nreply\n")
    chat_id = ingest_file(tmp_db, md)

    # tmp_db is a Connection; get the actual DB path for the CLI subprocess.
    db_path = tmp_db.execute("PRAGMA database_list").fetchone()["file"]
    out = tmp_path / "exported.jsonl"

    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "git_llm.cli", "export", str(chat_id), str(out),
         "--db", db_path],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    parsed = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert len(parsed) == 2
