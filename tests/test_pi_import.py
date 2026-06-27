"""Tests for the pi.dev agent session JSONL adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from git_llm.ingest import ingest_file, parse_file, parse_jsonl
from git_llm.pi_import import is_pi_session, parse_pi_file, parse_pi_session
from git_llm.schema import ChatExport
from git_llm.taxonomy import Role

FIXTURE = Path(__file__).parent / "fixtures" / "pi-session-mini.jsonl"


# ---------- Detection ---------------------------------------------------------

def test_is_pi_session_detects_header():
    first = '{"type":"session","version":3,"id":"x","timestamp":"2026-06-27T00:00:00Z","cwd":"/x"}'
    assert is_pi_session(first) is True


def test_is_pi_session_rejects_canonical_turn():
    assert is_pi_session('{"role":"user","content":"hi"}') is False


def test_is_pi_session_rejects_malformed():
    assert is_pi_session("not json") is False
    assert is_pi_session("") is False


# ---------- Parsing -----------------------------------------------------------

@pytest.fixture
def pi_export() -> ChatExport:
    return parse_pi_file(FIXTURE)


def test_session_header_becomes_metadata(pi_export: ChatExport):
    assert pi_export.title == "demo-repo"
    assert pi_export.metadata["cwd"] == "/Users/demo/PycharmProjects/demo-repo"
    assert pi_export.metadata["session_id"] == "sess-abc"
    assert pi_export.metadata["pi_version"] == 3
    assert pi_export.created_at is not None


def test_messages_count_excludes_control_lines(pi_export: ChatExport):
    # fixture has: session, model_change, thinking_level_change, user, assistant,
    # model_change, user → 3 messages total
    assert len(pi_export.messages) == 3


def test_dag_parent_id_preserved(pi_export: ChatExport):
    user_turn = pi_export.messages[0]
    assistant_turn = pi_export.messages[1]
    second_user = pi_export.messages[2]
    assert user_turn.id == "u1"
    assert assistant_turn.id == "a1"
    assert assistant_turn.parent_id == "u1"
    assert second_user.parent_id == "m2"  # follows a model change


def test_thinking_block_is_first_class(pi_export: ChatExport):
    assistant_turn = pi_export.messages[1]
    blocks = assistant_turn.content
    assert isinstance(blocks, list)
    thinking_blocks = [b for b in blocks if b.type == "thinking"]
    assert len(thinking_blocks) == 1
    assert thinking_blocks[0].thinking == "User wants a comparison."


def test_tool_call_normalized_to_tool_use(pi_export: ChatExport):
    assistant_turn = pi_export.messages[1]
    blocks = assistant_turn.content
    assert isinstance(blocks, list)
    tool_blocks = [b for b in blocks if b.type == "tool_use"]
    assert len(tool_blocks) == 1
    assert tool_blocks[0].name == "read_file"


def test_usage_normalized_to_snake_case(pi_export: ChatExport):
    assistant = pi_export.messages[1]
    assert assistant.usage is not None
    assert assistant.usage.input_tokens == 42
    assert assistant.usage.output_tokens == 128
    assert assistant.usage.cache_read_tokens == 1000
    assert assistant.usage.cache_write_tokens == 50
    assert assistant.usage.total_tokens == 1220
    assert assistant.usage.cost_usd == pytest.approx(0.0021)


def test_provider_metadata_captured(pi_export: ChatExport):
    assistant = pi_export.messages[1]
    assert assistant.metadata["provider"] == "anthropic"
    assert assistant.metadata["api"] == "anthropic-messages"
    assert assistant.metadata["stopReason"] == "stop"
    assert assistant.metadata["responseId"] == "resp-xyz"


def test_control_events_attached_to_next_message(pi_export: ChatExport):
    # The first user message should carry the initial model_change and
    # thinking_level_change events that preceded it.
    first_user = pi_export.messages[0]
    events = first_user.metadata.get("control_events", [])
    assert any(e.get("type") == "model_change" for e in events)
    assert any(e.get("type") == "thinking_level_change" for e in events)
    # The second user message gets the mid-session model_change.
    second_user = pi_export.messages[2]
    events2 = second_user.metadata.get("control_events", [])
    assert any(
        e.get("type") == "model_change" and e.get("modelId") == "claude-haiku-4"
        for e in events2
    )


def test_to_text_includes_thinking_marker(pi_export: ChatExport):
    assistant = pi_export.messages[1]
    text = assistant.to_text()
    assert "[thinking]" in text
    assert "User wants a comparison." in text
    assert "It has DAG support." in text
    assert "[tool_use:read_file]" in text


# ---------- Auto-detection in parse_jsonl -------------------------------------

def test_parse_jsonl_auto_routes_pi_format():
    text = FIXTURE.read_text()
    export, turns = parse_jsonl(text)
    assert export.metadata.get("cwd") == "/Users/demo/PycharmProjects/demo-repo"
    # 3 messages → 3 turns (no system messages in pi)
    assert len(turns) == 3


def test_parse_file_dispatch_uses_pi_for_jsonl():
    export, turns = parse_file(FIXTURE)
    assert export is not None and export.title == "demo-repo"
    assert turns[0][0] == Role.USER


# ---------- End-to-end via DB -------------------------------------------------

def test_ingest_pi_session_persists(tmp_db):
    chat_id = ingest_file(tmp_db, FIXTURE)
    row = tmp_db.execute(
        "SELECT title, COUNT(*) AS n FROM turns t "
        "JOIN chats c ON c.id = t.chat_id WHERE c.id = ?",
        (chat_id,),
    ).fetchone()
    assert row["title"] == "demo-repo"
    assert row["n"] == 3


def test_thinking_content_searchable_via_fts(tmp_db):
    chat_id = ingest_file(tmp_db, FIXTURE)
    # The thinking trace ("User wants a comparison") should be FTS-indexed.
    hits = tmp_db.execute(
        "SELECT t.idx FROM turns_fts f JOIN turns t ON t.id = f.rowid "
        "WHERE f.content MATCH ? AND t.chat_id = ?",
        ("comparison", chat_id),
    ).fetchall()
    assert hits, "Thinking-block content must be discoverable via FTS5"


# ---------- Robustness --------------------------------------------------------

def test_unknown_line_type_does_not_crash(tmp_path: Path):
    weird = (
        '{"type":"session","version":3,"id":"x","timestamp":"2026-06-27T00:00:00Z","cwd":"/x"}\n'
        '{"type":"future_unknown_event","id":"q","parentId":null}\n'
        '{"type":"message","id":"u","parentId":"q","timestamp":"2026-06-27T00:00:01Z",'
        '"message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n'
    )
    p = tmp_path / "weird.jsonl"
    p.write_text(weird)
    export = parse_pi_file(p)
    assert len(export.messages) == 1
    events = export.messages[0].metadata.get("control_events", [])
    assert any(e.get("type") == "future_unknown_event" for e in events)


def test_malformed_line_raises_with_lineno(tmp_path: Path):
    bad = (
        '{"type":"session","version":3,"id":"x","timestamp":"2026-06-27T00:00:00Z","cwd":"/x"}\n'
        "{not json}\n"
    )
    p = tmp_path / "bad.jsonl"
    p.write_text(bad)
    with pytest.raises(ValueError, match="line 2"):
        parse_pi_file(p)
