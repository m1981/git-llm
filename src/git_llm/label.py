"""
Turn-level dialogue act labeling.

Two labelers ship:
    - StubLabeler: deterministic, regex/heuristic-based. Used for tests and
      offline runs. Good enough as a first pass on most chats.
    - LLMLabeler: uses LiteLLM to delegate classification to any provider
      (OpenAI, Anthropic, Gemini, Ollama). Returns multiple labels per turn.

Both implement the same Protocol so the CLI can swap them transparently.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Protocol

from git_llm.models import Turn
from git_llm.taxonomy import (
    ASSISTANT_LABELS,
    BY_NAME,
    LABELS,
    USER_LABELS,
    Role,
)


class Labeler(Protocol):
    name: str

    def label(self, turn: Turn) -> list[tuple[str, float]]: ...


# ---------------------------------------------------------------------------
# Heuristic / stub labeler
# ---------------------------------------------------------------------------

_QUESTION_RE = re.compile(r"\?\s*$", re.MULTILINE)
_CODE_RE = re.compile(r"```|^\s{4}\S", re.MULTILINE)
_DIRECTIVE_RE = re.compile(r"\b(please|make|build|generate|write|give|show)\b", re.IGNORECASE)
_PIVOT_RE = re.compile(r"\b(actually|instead|let'?s switch|pivot|change to)\b", re.IGNORECASE)
_REFLECT_RE = re.compile(r"\b(looking back|previously|earlier we|in retrospect)\b", re.IGNORECASE)
_VALIDATION_RE = re.compile(r"\b(does this look|is this right|critique|review|opinion)\b", re.IGNORECASE)
_CHALLENGE_RE = re.compile(r"\b(but |however|disagree|wrong|are you sure)\b", re.IGNORECASE)
_WARNING_RE = re.compile(r"\b(warning|risk|caveat|beware|anti-?pattern|pitfall)\b", re.IGNORECASE)
_EDUCATIONAL_RE = re.compile(r"\b(concept|theory|principle|in essence|fundamentally)\b", re.IGNORECASE)
_DIAGRAM_RE = re.compile(r"```mermaid|graph (TD|LR|TB)|sequenceDiagram", re.IGNORECASE)
_PRAGMATIC_RE = re.compile(r"\b(trade-?off|compromise|pragmatic|in practice|real-?world)\b", re.IGNORECASE)


class StubLabeler:
    name = "stub"

    def label(self, turn: Turn) -> list[tuple[str, float]]:
        text = turn.content
        out: list[tuple[str, float]] = []

        if turn.role == Role.USER:
            if _QUESTION_RE.search(text):
                out.append(("Inquiring", 0.7))
            if _CODE_RE.search(text):
                out.append(("Providing-Context", 0.8))
            if _DIRECTIVE_RE.search(text):
                out.append(("Directing", 0.6))
            if _PIVOT_RE.search(text):
                out.append(("Pivoting", 0.8))
            if _REFLECT_RE.search(text):
                out.append(("Reflective", 0.7))
            if _VALIDATION_RE.search(text):
                out.append(("Seeking-Validation", 0.75))
            if _CHALLENGE_RE.search(text):
                out.append(("Challenging", 0.65))
            if not out:
                out.append(("Inquiring", 0.4))  # default
        else:  # assistant
            if _DIAGRAM_RE.search(text):
                out.append(("Visualizing", 0.9))
            if _EDUCATIONAL_RE.search(text):
                out.append(("Educational", 0.75))
            if _PRAGMATIC_RE.search(text):
                out.append(("Pragmatic", 0.8))
            if _WARNING_RE.search(text):
                out.append(("Warning", 0.8))
            if _CODE_RE.search(text):
                out.append(("Prescriptive", 0.6))
            if re.search(r"\b(fix|incorrect|mistake|actually,? )\b", text, re.IGNORECASE):
                out.append(("Correcting", 0.6))
            if re.search(r"\b(folder|structure|organize|layout)\b", text, re.IGNORECASE):
                out.append(("Structuring", 0.55))
            if re.search(r"\b(in summary|to summarize|overall|bringing together)\b", text, re.IGNORECASE):
                out.append(("Synthesizing", 0.6))
            if not out:
                out.append(("Analytical", 0.4))

        # dedupe, keep highest confidence per label
        best: dict[str, float] = {}
        for name, conf in out:
            best[name] = max(best.get(name, 0.0), conf)
        return sorted(best.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# LLM-as-classifier
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """\
You are a dialogue act classifier for software-engineering LLM chats.

You will receive ONE turn at a time and must return a JSON object:
  {"labels": [{"name": "<LabelName>", "confidence": <0..1>}, ...]}

Rules:
- Pick 1 to 3 labels. Multiple labels are encouraged when the turn does
  several things (e.g., directs AND provides context).
- ONLY use labels from the provided dictionary. Never invent new ones.
- Return strict JSON. No prose, no markdown fences.
"""


def _build_user_prompt(turn: Turn) -> str:
    if turn.role == Role.USER:
        catalog = USER_LABELS
    else:
        catalog = ASSISTANT_LABELS
    descriptions = "\n".join(f"- {n}: {BY_NAME[n].description}" for n in catalog)
    return (
        f"Role: {turn.role.value}\n"
        f"Allowed labels:\n{descriptions}\n\n"
        f"--- TURN CONTENT ---\n{turn.content[:4000]}\n--- END ---"
    )


class LLMLabeler:
    """LiteLLM-backed classifier. Model defaults to a cheap fast option."""

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0) -> None:
        self.model = model
        self.temperature = temperature
        self.name = f"llm:{model}"

    def label(self, turn: Turn) -> list[tuple[str, float]]:
        # Lazy import so the stub path stays dependency-light.
        from litellm import completion  # type: ignore

        resp = completion(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(turn)},
            ],
        )
        raw = resp["choices"][0]["message"]["content"]

        # Strip markdown code fences that Claude and some models wrap JSON in
        raw = raw.strip()
        if raw.startswith("```"):
            # Remove opening fence (with optional language tag) and closing fence
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []

        out: list[tuple[str, float]] = []
        for item in payload.get("labels", []):
            name = str(item.get("name", "")).strip()
            if name in {l.name for l in LABELS}:
                conf = float(item.get("confidence", 0.5))
                out.append((name, max(0.0, min(1.0, conf))))
        return out


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def label_chat(
    conn: sqlite3.Connection,
    chat_id: int,
    labeler: Labeler,
    role: str | None = None,
) -> int:
    """Label turns in a chat; replace any prior labels from this labeler.

    Args:
        role: If set (e.g. 'user' or 'assistant'), only label turns with this role.
              If None, label every turn.
    """
    sql = (
        "SELECT id, chat_id, idx, role, content, token_estimate "
        "FROM turns WHERE chat_id = ?"
    )
    params: list[object] = [chat_id]
    if role is not None:
        sql += " AND role = ?"
        params.append(role)
    sql += " ORDER BY idx"
    rows = conn.execute(sql, params).fetchall()

    n_inserted = 0
    for row in rows:
        turn = Turn(**dict(row))
        assert turn.id is not None
        conn.execute(
            "DELETE FROM labels WHERE turn_id = ? AND labeler = ?",
            (turn.id, labeler.name),
        )
        for name, conf in labeler.label(turn):
            spec = BY_NAME[name]
            conn.execute(
                "INSERT OR IGNORE INTO labels "
                "(turn_id, name, master_class, confidence, labeler) "
                "VALUES (?, ?, ?, ?, ?)",
                (turn.id, name, spec.master_class.value, conf, labeler.name),
            )
            n_inserted += 1
    conn.commit()
    return n_inserted
