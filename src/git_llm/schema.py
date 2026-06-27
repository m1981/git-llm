"""
Canonical chat-export schema.

JSONL is the source-of-truth format. JSON (array or envelope) is accepted for
compatibility with OpenAI / Anthropic / ChatGPT-export shapes. Markdown is a
best-effort import only.

A `TurnExport` mirrors the de-facto OpenAI/Anthropic `messages` shape so that
exports from those providers ingest with zero translation:

    {"role": "user", "content": "..."}
    {"role": "assistant", "content": [{"type": "text", "text": "..."}, ...]}

v0.2 additions (driven by comparison to pi-session-export format):
    - `parent_id`  : DAG support so branches/regenerations are preserved.
    - `usage`      : per-turn token + cost telemetry.
    - `thinking`   : first-class content block for reasoning traces.

Non-text blocks (image, tool_use, tool_result) are flattened to text markers
on `.to_text()` so the original turn count and ordering are never lost.
Thinking blocks are flattened with a `[thinking]` prefix so the labeler can
both find them (FTS5) and distinguish them from the visible answer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class UsageInfo(BaseModel):
    """Per-turn token + cost telemetry (optional; populated when available)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None

    model_config = {"extra": "ignore"}

    def to_dict(self) -> dict[str, Any]:
        """Serialize using Pydantic field names for lossless roundtrip.

        Keys match ``UsageInfo`` field names (``input_tokens``, ``cost_usd``)
        so that ``UsageInfo.model_validate(usage.to_dict())`` is identity.
        """
        return self.model_dump(exclude_none=True)


class ContentBlock(BaseModel):
    """OpenAI / Anthropic-style content block, extended with `thinking`."""

    type: str  # "text" | "image" | "thinking" | "tool_use" | "tool_result" | ...
    text: str | None = None
    thinking: str | None = None  # reasoning trace (Claude, o1, R1, ...)
    name: str | None = None      # for tool_use
    # any other fields are tolerated but ignored
    model_config = {"extra": "allow"}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to pi-compatible content block shape."""
        d: dict[str, Any] = {"type": self.type}
        if self.text is not None:
            d["text"] = self.text
        if self.thinking is not None:
            d["thinking"] = self.thinking
        if self.name is not None:
            d["name"] = self.name
        return d


class TurnExport(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str | list[ContentBlock]
    timestamp: datetime | None = None
    model: str | None = None
    id: str | None = None
    parent_id: str | None = None       # DAG edge: previous turn this replied to
    usage: UsageInfo | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Tolerant of provider-specific extras at the top level (camelCase, etc.).
    model_config = {"extra": "ignore"}

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_content(cls, v: Any) -> Any:
        return v

    def to_text(self) -> str:
        """Flatten content blocks to plain text, preserving non-text markers."""
        if isinstance(self.content, str):
            return self.content
        parts: list[str] = []
        for block in self.content:
            if block.type == "text" and block.text:
                parts.append(block.text)
            elif block.type == "thinking" and block.thinking:
                # Prefix so the labeler can detect reasoning traces while
                # FTS5 still finds the words inside.
                parts.append(f"[thinking]\n{block.thinking}")
            elif block.type == "image":
                parts.append("[image]")
            elif block.type == "tool_use":
                parts.append(f"[tool_use:{block.name or '?'}]")
            elif block.type == "tool_result":
                parts.append("[tool_result]")
            else:
                parts.append(f"[{block.type}]")
        return "\n".join(parts).strip()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to canonical JSONL-compatible dict."""
        content: str | list[dict[str, Any]]
        if isinstance(self.content, str):
            content = self.content
        else:
            content = [block.to_dict() for block in self.content]

        msg: dict[str, Any] = {"role": self.role, "content": content}

        if self.timestamp is not None:
            msg["timestamp"] = self.timestamp.isoformat()
        if self.model is not None:
            msg["model"] = self.model
        if self.id is not None:
            msg["id"] = self.id
        if self.parent_id is not None:
            msg["parent_id"] = self.parent_id
        if self.usage is not None:
            msg["usage"] = self.usage.to_dict()
        if self.metadata:
            msg["metadata"] = self.metadata

        return msg


class ChatExport(BaseModel):
    """Top-level envelope for a chat export."""

    title: str | None = None
    model: str | None = None
    created_at: datetime | None = None
    messages: list[TurnExport]
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to canonical JSON envelope dict.

        ``ChatExport.metadata`` keys are promoted to the top level of the
        envelope (alongside ``title``, ``model``, etc.) so that roundtripping
        through ``parse_json`` reproduces the original flat metadata dict.
        """
        envelope: dict[str, Any] = {"messages": [m.to_dict() for m in self.messages]}
        if self.title is not None:
            envelope["title"] = self.title
        if self.model is not None:
            envelope["model"] = self.model
        if self.created_at is not None:
            envelope["created_at"] = self.created_at.isoformat()
        # Promote metadata keys to top-level so parse_json can recover them.
        for k, v in self.metadata.items():
            envelope[k] = v
        return envelope
