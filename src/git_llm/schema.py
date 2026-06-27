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


class ContentBlock(BaseModel):
    """OpenAI / Anthropic-style content block, extended with `thinking`."""

    type: str  # "text" | "image" | "thinking" | "tool_use" | "tool_result" | ...
    text: str | None = None
    thinking: str | None = None  # reasoning trace (Claude, o1, R1, ...)
    name: str | None = None      # for tool_use
    # any other fields are tolerated but ignored
    model_config = {"extra": "allow"}


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


class ChatExport(BaseModel):
    """Top-level envelope for a chat export."""

    title: str | None = None
    model: str | None = None
    created_at: datetime | None = None
    messages: list[TurnExport]
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}
