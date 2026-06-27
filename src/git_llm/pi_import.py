"""
Adapter: pi.dev agent session JSONL → canonical `ChatExport`.

Pi sessions live at `~/.pi/agent/sessions/<cwd-encoded>/<timestamp>_<uuid>.jsonl`
and use a *heterogeneous* line format — every line carries a `type` field:

    {"type": "session",               "id": "...", "cwd": "...", "timestamp": "...", "version": 3}
    {"type": "model_change",          "id": "...", "parentId": "...", "provider": "...", "modelId": "..."}
    {"type": "thinking_level_change", "id": "...", "parentId": "...", "thinkingLevel": "high"}
    {"type": "message",               "id": "...", "parentId": "...", "timestamp": "...",
        "message": {"role": "user|assistant", "content": [...],
                    "model": "...", "provider": "...", "api": "...",
                    "stopReason": "...", "responseId": "...",
                    "usage": {"input": N, "output": N, "cacheRead": N, "cacheWrite": N,
                              "totalTokens": N, "cost": {"input": $, ..., "total": $}}}}

Mapping rules:
    - `session`                 → ChatExport.title (basename of cwd) + metadata.cwd / session_id / version
    - `model_change`            → buffered into metadata.control_events; attached to the *next* message
    - `thinking_level_change`   → same buffer
    - `message`                 → one TurnExport; content blocks normalized:
        - `text`       → ContentBlock(type="text", text=...)
        - `thinking`   → ContentBlock(type="thinking", thinking=...)  ← first-class
        - `toolCall`   → ContentBlock(type="tool_use", name=...)
    - `message.usage`           → TurnExport.usage  (note: pi uses `input`/`output`/`cacheRead`/`cacheWrite`;
                                                     we normalize to snake_case)
    - `message.parentId`        → TurnExport.parent_id (DAG edge)
    - api/provider/stopReason/responseId → TurnExport.metadata (provider telemetry, not labeling input)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from git_llm.schema import ChatExport, ContentBlock, TurnExport, UsageInfo

_CONTROL_TYPES = {"model_change", "thinking_level_change"}
_ROLES = {"user", "assistant", "system"}


def is_pi_session(first_line: str) -> bool:
    """Cheap sniff: pi sessions always start with a `type=session` header line."""
    try:
        d = json.loads(first_line)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(d, dict) and d.get("type") == "session"


def _convert_usage(raw: dict[str, Any] | None) -> UsageInfo | None:
    if not raw:
        return None
    cost = raw.get("cost") or {}
    cost_total = cost.get("total") if isinstance(cost, dict) else None
    return UsageInfo(
        input_tokens=raw.get("input"),
        output_tokens=raw.get("output"),
        cache_read_tokens=raw.get("cacheRead"),
        cache_write_tokens=raw.get("cacheWrite"),
        total_tokens=raw.get("totalTokens"),
        cost_usd=cost_total,
    )


def _convert_blocks(raw_blocks: list[dict[str, Any]]) -> list[ContentBlock]:
    out: list[ContentBlock] = []
    for b in raw_blocks:
        bt = b.get("type")
        if bt == "text":
            out.append(ContentBlock(type="text", text=b.get("text", "")))
        elif bt == "thinking":
            out.append(ContentBlock(type="thinking", thinking=b.get("thinking", "")))
        elif bt == "toolCall":
            # pi uses camelCase + sometimes `toolName`; we normalize to OpenAI/Anthropic snake_case.
            out.append(
                ContentBlock(
                    type="tool_use",
                    name=b.get("name") or b.get("toolName") or b.get("tool"),
                )
            )
        elif bt == "toolResult":
            out.append(ContentBlock(type="tool_result"))
        elif bt == "image":
            out.append(ContentBlock(type="image"))
        elif bt:
            out.append(ContentBlock(type=bt))
    return out


def parse_pi_session(text: str) -> ChatExport:
    """Parse a complete pi session file (full text) into a ChatExport."""
    title: str | None = None
    cwd: str | None = None
    session_id: str | None = None
    version: int | None = None
    created_at_iso: str | None = None
    dominant_model: str | None = None

    pending_events: list[dict[str, Any]] = []
    turns: list[TurnExport] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"pi session line {lineno} is not valid JSON: {e}") from e

        kind = d.get("type")

        if kind == "session":
            session_id = d.get("id")
            cwd = d.get("cwd")
            created_at_iso = d.get("timestamp")
            version = d.get("version")
            title = (Path(cwd).name if cwd else session_id) or "pi-session"
            continue

        if kind in _CONTROL_TYPES:
            pending_events.append(
                {k: v for k, v in d.items() if k not in {"id", "parentId"}}
            )
            continue

        if kind != "message":
            # Unknown line type — preserve it as a control event for forensics.
            pending_events.append({"type": kind, **{k: v for k, v in d.items() if k != "type"}})
            continue

        msg = d.get("message") or {}
        role = msg.get("role")
        if role not in _ROLES:
            continue

        content_raw = msg.get("content")
        if isinstance(content_raw, str):
            blocks: list[ContentBlock] | str = content_raw
        elif isinstance(content_raw, list):
            blocks = _convert_blocks(content_raw)
        else:
            blocks = []

        metadata: dict[str, Any] = {}
        for key in ("api", "provider", "stopReason", "responseId"):
            if msg.get(key) is not None:
                metadata[key] = msg[key]
        if pending_events:
            metadata["control_events"] = pending_events
            pending_events = []

        model = msg.get("model")
        if model and not dominant_model:
            dominant_model = model

        turns.append(
            TurnExport(
                role=role,
                content=blocks,
                timestamp=d.get("timestamp"),
                model=model,
                id=d.get("id"),
                parent_id=d.get("parentId"),
                usage=_convert_usage(msg.get("usage")),
                metadata=metadata,
            )
        )

    chat_metadata: dict[str, Any] = {}
    if cwd:
        chat_metadata["cwd"] = cwd
    if session_id:
        chat_metadata["session_id"] = session_id
    if version is not None:
        chat_metadata["pi_version"] = version
    # If there are trailing control events with no following message, keep them.
    if pending_events:
        chat_metadata["trailing_control_events"] = pending_events

    return ChatExport(
        title=title or "pi-session",
        model=dominant_model,
        created_at=created_at_iso,
        messages=turns,
        metadata=chat_metadata,
    )


def parse_pi_file(path: Path) -> ChatExport:
    return parse_pi_session(path.read_text(encoding="utf-8"))
