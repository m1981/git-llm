"""Tests for the canonical export pipeline.

Validates:
    - Roundtrip fidelity: pi JSONL → ChatExport → JSON → ChatExport
    - Schema correctness of serialized output
    - Field normalization (snake_case ↔ camelCase)
    - Idempotency (double-export produces identical output)
    - Edge cases (empty sessions, string content, metadata preservation)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from git_llm.export import export_json, export_jsonl, write_json
from git_llm.ingest import parse_json
from git_llm.pi_import import parse_pi_file
from git_llm.schema import ChatExport, ContentBlock, TurnExport, UsageInfo
from git_llm.taxonomy import Role

FIXTURE = Path(__file__).parent / "fixtures" / "pi-session-mini.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def pi_export() -> ChatExport:
    """Parse the golden pi fixture into a ChatExport."""
    return parse_pi_file(FIXTURE)


@pytest.fixture
def sample_export() -> ChatExport:
    """Minimal hand-crafted ChatExport for unit tests."""
    return ChatExport(
        title="unit-test",
        model="gpt-4o",
        created_at=datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc),
        messages=[
            TurnExport(
                role="user",
                content="Hello world",
                timestamp=datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc),
                id="t1",
            ),
            TurnExport(
                role="assistant",
                content=[
                    ContentBlock(type="text", text="Hi there!"),
                    ContentBlock(type="thinking", thinking="User says hello"),
                ],
                timestamp=datetime(2026, 6, 28, 12, 0, 5, tzinfo=timezone.utc),
                model="gpt-4o",
                id="t2",
                parent_id="t1",
                usage=UsageInfo(
                    input_tokens=10,
                    output_tokens=20,
                    cache_read_tokens=5,
                    total_tokens=35,
                    cost_usd=0.001,
                ),
                metadata={"provider": "openai"},
            ),
        ],
        metadata={"source": "unit-test"},
    )


# ---------------------------------------------------------------------------
# 1. Schema-level to_dict tests
# ---------------------------------------------------------------------------

class TestUsageInfoSerialization:
    def test_all_fields(self):
        u = UsageInfo(
            input_tokens=100,
            output_tokens=200,
            cache_read_tokens=50,
            cache_write_tokens=10,
            total_tokens=360,
            cost_usd=0.05,
        )
        d = u.to_dict()
        # Field names match Pydantic model for lossless roundtrip.
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 200
        assert d["cache_read_tokens"] == 50
        assert d["cache_write_tokens"] == 10
        assert d["total_tokens"] == 360
        assert d["cost_usd"] == pytest.approx(0.05)

    def test_none_fields_omitted(self):
        u = UsageInfo(input_tokens=10)
        d = u.to_dict()
        assert "input_tokens" in d
        assert "output_tokens" not in d
        assert "cost_usd" not in d

    def test_empty(self):
        u = UsageInfo()
        assert u.to_dict() == {}


class TestContentBlockSerialization:
    def test_text_block(self):
        b = ContentBlock(type="text", text="hello")
        d = b.to_dict()
        assert d == {"type": "text", "text": "hello"}

    def test_thinking_block(self):
        b = ContentBlock(type="thinking", thinking="reasoning...")
        d = b.to_dict()
        assert d == {"type": "thinking", "thinking": "reasoning..."}

    def test_tool_use_block(self):
        b = ContentBlock(type="tool_use", name="read_file")
        d = b.to_dict()
        assert d == {"type": "tool_use", "name": "read_file"}

    def test_none_fields_omitted(self):
        b = ContentBlock(type="image")
        d = b.to_dict()
        assert d == {"type": "image"}


class TestTurnExportSerialization:
    def test_string_content(self):
        t = TurnExport(role="user", content="hello")
        d = t.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "hello"

    def test_block_content(self):
        t = TurnExport(
            role="assistant",
            content=[ContentBlock(type="text", text="ok")],
        )
        d = t.to_dict()
        assert isinstance(d["content"], list)
        assert d["content"][0] == {"type": "text", "text": "ok"}

    def test_optional_fields_serialized(self):
        t = TurnExport(
            role="assistant",
            content="x",
            id="a1",
            parent_id="u1",
            model="claude",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            usage=UsageInfo(input_tokens=1),
            metadata={"k": "v"},
        )
        d = t.to_dict()
        assert d["id"] == "a1"
        assert d["parent_id"] == "u1"
        assert d["model"] == "claude"
        assert "timestamp" in d
        assert d["usage"]["input_tokens"] == 1
        assert d["metadata"] == {"k": "v"}

    def test_none_optional_fields_omitted(self):
        t = TurnExport(role="user", content="x")
        d = t.to_dict()
        assert "id" not in d
        assert "parent_id" not in d
        assert "model" not in d
        assert "usage" not in d
        assert "metadata" not in d


class TestChatExportSerialization:
    def test_envelope_structure(self, sample_export: ChatExport):
        d = sample_export.to_dict()
        assert d["title"] == "unit-test"
        assert d["model"] == "gpt-4o"
        assert "created_at" in d
        # Metadata keys are promoted to top level (not nested).
        assert d["source"] == "unit-test"
        assert len(d["messages"]) == 2

    def test_minimal_envelope(self):
        e = ChatExport(messages=[TurnExport(role="user", content="x")])
        d = e.to_dict()
        assert "title" not in d
        assert "model" not in d
        assert "created_at" not in d
        assert len(d["messages"]) == 1


# ---------------------------------------------------------------------------
# 2. export_json / export_jsonl
# ---------------------------------------------------------------------------

class TestExportJson:
    def test_produces_valid_json(self, sample_export: ChatExport):
        raw = export_json(sample_export)
        data = json.loads(raw)
        assert isinstance(data, dict)
        assert "messages" in data

    def test_json_parseable_by_ingest(self, sample_export: ChatExport):
        raw = export_json(sample_export)
        reimported, turns = parse_json(raw)
        assert reimported.title == "unit-test"
        assert len(turns) == 2
        assert turns[0] == (Role.USER, "Hello world")

    def test_thinking_block_survives(self, sample_export: ChatExport):
        raw = export_json(sample_export)
        data = json.loads(raw)
        assistant = data["messages"][1]
        blocks = assistant["content"]
        thinking = [b for b in blocks if b["type"] == "thinking"]
        assert len(thinking) == 1
        assert thinking[0]["thinking"] == "User says hello"


class TestExportJsonl:
    def test_one_line_per_message(self, sample_export: ChatExport):
        raw = export_jsonl(sample_export)
        lines = [l for l in raw.splitlines() if l.strip()]
        assert len(lines) == 2

    def test_each_line_valid_json(self, sample_export: ChatExport):
        raw = export_jsonl(sample_export)
        for line in raw.splitlines():
            if line.strip():
                obj = json.loads(line)
                assert "role" in obj
                assert "content" in obj


# ---------------------------------------------------------------------------
# 3. Roundtrip: pi → ChatExport → JSON → ChatExport
# ---------------------------------------------------------------------------

class TestRoundtrip:
    def test_message_count_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        assert len(reimported.messages) == len(pi_export.messages)

    def test_roles_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        for orig, reim in zip(pi_export.messages, reimported.messages):
            assert orig.role == reim.role

    def test_content_text_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        for orig, reim in zip(pi_export.messages, reimported.messages):
            assert reim.to_text() == orig.to_text()

    def test_title_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        assert reimported.title == pi_export.title

    def test_model_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        assert reimported.model == pi_export.model

    def test_dag_ids_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        for orig, reim in zip(pi_export.messages, reimported.messages):
            assert reim.id == orig.id
            assert reim.parent_id == orig.parent_id

    def test_usage_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        # Second message (assistant) has usage
        orig_usage = pi_export.messages[1].usage
        reim_usage = reimported.messages[1].usage
        assert orig_usage is not None
        assert reim_usage is not None
        assert reim_usage.input_tokens == orig_usage.input_tokens
        assert reim_usage.output_tokens == orig_usage.output_tokens
        assert reim_usage.cache_read_tokens == orig_usage.cache_read_tokens
        assert reim_usage.total_tokens == orig_usage.total_tokens
        assert reim_usage.cost_usd == pytest.approx(orig_usage.cost_usd)

    def test_metadata_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        assert reimported.metadata.get("cwd") == pi_export.metadata.get("cwd")
        assert reimported.metadata.get("session_id") == pi_export.metadata.get("session_id")

    def test_thinking_blocks_preserved(self, pi_export: ChatExport):
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        assistant = reimported.messages[1]
        thinking = [b for b in assistant.content if b.type == "thinking"]
        assert len(thinking) == 1
        assert thinking[0].thinking == "User wants a comparison."

    def test_flatten_turns_equivalent(self, pi_export: ChatExport):
        """The flattened (role, text) tuples must be identical after roundtrip."""
        raw = export_json(pi_export)
        _, orig_turns_raw = parse_json(export_json(pi_export))
        _, reim_turns = parse_json(raw)
        assert len(orig_turns_raw) == len(reim_turns)
        for (r1, t1), (r2, t2) in zip(orig_turns_raw, reim_turns):
            assert r1 == r2
            assert t1 == t2


# ---------------------------------------------------------------------------
# 4. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_double_export_identical(self, pi_export: ChatExport):
        first = export_json(pi_export)
        reimported, _ = parse_json(first)
        second = export_json(reimported)
        assert json.loads(first) == json.loads(second)


# ---------------------------------------------------------------------------
# 5. write_json (file IO)
# ---------------------------------------------------------------------------

class TestWriteJson:
    def test_creates_file(self, sample_export: ChatExport, tmp_path: Path):
        out = tmp_path / "sub" / "export.json"
        result = write_json(sample_export, out)
        assert result == out
        assert out.exists()

    def test_written_file_reimportable(self, sample_export: ChatExport, tmp_path: Path):
        out = tmp_path / "export.json"
        write_json(sample_export, out)
        reimported, turns = parse_json(out.read_text())
        assert reimported.title == "unit-test"
        assert len(turns) == 2


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_messages(self):
        export = ChatExport(messages=[], title="empty")
        raw = export_json(export)
        data = json.loads(raw)
        assert data["messages"] == []
        assert data["title"] == "empty"

    def test_string_content_roundtrip(self):
        export = ChatExport(
            messages=[
                TurnExport(role="user", content="plain string"),
                TurnExport(role="assistant", content="also string"),
            ]
        )
        raw = export_json(export)
        reimported, turns = parse_json(raw)
        assert turns[0][1] == "plain string"
        assert turns[1][1] == "also string"

    def test_control_events_in_metadata_survive(self, pi_export: ChatExport):
        """Control events attached during pi import survive export roundtrip."""
        raw = export_json(pi_export)
        reimported, _ = parse_json(raw)
        first_msg = reimported.messages[0]
        events = first_msg.metadata.get("control_events", [])
        assert len(events) > 0
        assert any(e.get("type") == "model_change" for e in events)

    def test_special_characters_in_content(self):
        export = ChatExport(
            messages=[
                TurnExport(role="user", content="emoji 🚀 and unicode ñ ü"),
                TurnExport(role="assistant", content='json {"key": "value"} inside'),
            ]
        )
        raw = export_json(export)
        reimported, turns = parse_json(raw)
        assert "🚀" in turns[0][1]
        assert '{"key":' in turns[1][1]
