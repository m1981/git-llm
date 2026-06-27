"""Tests for the hardened parsers and JSONL canonical format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from git_llm.ingest import (
    ingest_file,
    md_to_jsonl,
    parse_json,
    parse_jsonl,
    parse_markdown,
)
from git_llm.taxonomy import Role


# ---------- markdown hardening -------------------------------------------------

def test_markdown_ignores_heading_inside_code_fence():
    text = (
        "# user\n"
        "How do I split turns?\n"
        "# AI\n"
        "Use a heading like this:\n"
        "```\n"
        "# user\n"          # ← MUST NOT split the AI turn
        "should stay\n"
        "```\n"
        "Got it?\n"
    )
    turns = parse_markdown(text)
    assert len(turns) == 2
    assert turns[0][0] == Role.USER
    assert turns[1][0] == Role.ASSISTANT
    assert "should stay" in turns[1][1]
    assert "```" in turns[1][1]


def test_markdown_ignores_tilde_fences():
    text = "# user\nq\n# AI\n~~~\n# user\n~~~\ndone\n"
    turns = parse_markdown(text)
    assert len(turns) == 2


def test_markdown_strict_raises_on_no_headings():
    with pytest.raises(ValueError):
        parse_markdown("just some prose, no headings here", strict=True)


def test_markdown_rejects_heading_with_trailing_text():
    # `# user notes` is NOT a turn boundary — only `# user` exactly.
    text = "# user notes\nthis is content\n# AI\nreply\n"
    turns = parse_markdown(text)
    # Only the `# AI` heading matched, so we get one assistant turn.
    # The `# user notes` line and what follows is buffered before any role
    # is set and therefore discarded — which is the safe behavior.
    assert all(r == Role.ASSISTANT for r, _ in turns)


# ---------- JSON / JSONL -------------------------------------------------------

def test_parse_json_bare_array():
    payload = json.dumps([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])
    export, turns = parse_json(payload)
    assert len(turns) == 2
    assert export.messages[0].role == "user"


def test_parse_json_openai_envelope():
    payload = json.dumps({
        "title": "demo",
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "be helpful"},     # dropped
            {"role": "user", "content": "ping"},
            {"role": "assistant", "content": "pong"},
        ],
    })
    export, turns = parse_json(payload)
    assert export.title == "demo"
    assert export.model == "gpt-4o-mini"
    assert len(turns) == 2  # system filtered out
    assert turns[0] == (Role.USER, "ping")


def test_parse_json_anthropic_content_blocks():
    payload = json.dumps({
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look at this"},
                    {"type": "image"},
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "search"},
                    {"type": "text", "text": "found it"},
                ],
            },
        ]
    })
    _, turns = parse_json(payload)
    assert "[image]" in turns[0][1]
    assert "look at this" in turns[0][1]
    assert "[tool_use:search]" in turns[1][1]
    assert "found it" in turns[1][1]


def test_parse_jsonl_roundtrip():
    src = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]
    jsonl = "\n".join(json.dumps(t) for t in src)
    _, turns = parse_jsonl(jsonl)
    assert [t[1] for t in turns] == ["q1", "a1", "q2"]


def test_parse_jsonl_invalid_line_reports_lineno():
    bad = '{"role":"user","content":"ok"}\n{not json}\n'
    with pytest.raises(ValueError, match="line 2"):
        parse_jsonl(bad)


# ---------- md → jsonl conversion ---------------------------------------------

def test_md_to_jsonl_is_robust():
    md = "# user\nhi\n# AI\nhello\n```\n# user\n```\n"
    jsonl = md_to_jsonl(md)
    lines = [l for l in jsonl.splitlines() if l.strip()]
    assert len(lines) == 2
    parsed = [json.loads(l) for l in lines]
    assert parsed[0]["role"] == "user"
    assert parsed[1]["role"] == "assistant"
    assert "# user" in parsed[1]["content"]  # code fence preserved verbatim


# ---------- end-to-end via DB -------------------------------------------------

def test_ingest_jsonl_file(tmp_db, tmp_path: Path):
    p = tmp_path / "chat.jsonl"
    p.write_text(
        '{"role":"user","content":"q"}\n{"role":"assistant","content":"a"}\n'
    )
    chat_id = ingest_file(tmp_db, p)
    n = tmp_db.execute(
        "SELECT COUNT(*) AS n FROM turns WHERE chat_id=?", (chat_id,)
    ).fetchone()["n"]
    assert n == 2


def test_ingest_json_envelope_file(tmp_db, tmp_path: Path):
    p = tmp_path / "chat.json"
    p.write_text(json.dumps({
        "title": "envelope test",
        "messages": [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ],
    }))
    chat_id = ingest_file(tmp_db, p)
    row = tmp_db.execute("SELECT title FROM chats WHERE id=?", (chat_id,)).fetchone()
    assert row["title"] == "envelope test"
