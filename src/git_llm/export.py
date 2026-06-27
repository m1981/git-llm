"""
Export `ChatExport` to canonical JSONL / JSON formats.

Design:
    - Pure functions: ChatExport → str (no side-effects except file writes in `write_*`).
    - Serialization is delegated to `schema.to_dict()` so field normalization
      lives in one place.
    - JSON envelope format is the primary output (preserves title, model,
      created_at, metadata). JSONL is emitted as the `messages` array contents,
      one TurnExport per line — suitable for streaming / appending.

Roundtrip contract:
    parse_json(export_json(export)) ≡ export   (modulo datetime precision)
"""

from __future__ import annotations

import json
from pathlib import Path

from git_llm.schema import ChatExport


def export_json(export: ChatExport) -> str:
    """Serialize ChatExport to a canonical JSON envelope string.

    The output conforms to the envelope shape accepted by
    ``ingest.parse_json``::

        {"title": "...", "model": "...", "created_at": "...",
         "metadata": {...}, "messages": [...]}
    """
    return json.dumps(export.to_dict(), ensure_ascii=False, indent=2)


def export_jsonl(export: ChatExport) -> str:
    """Serialize ChatExport messages to canonical JSONL (one turn per line).

    Note: top-level metadata (title, model, created_at) is *not* represented
    in pure JSONL.  Use ``export_json`` when you need the full envelope.
    """
    lines = [
        json.dumps(m.to_dict(), ensure_ascii=False)
        for m in export.messages
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def write_json(export: ChatExport, path: Path) -> Path:
    """Write ChatExport to a JSON envelope file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_json(export), encoding="utf-8")
    return path


def write_jsonl(export: ChatExport, path: Path) -> Path:
    """Write ChatExport messages to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_jsonl(export), encoding="utf-8")
    return path
