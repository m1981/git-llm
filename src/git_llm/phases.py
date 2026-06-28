"""
Macro-phase compression via adjacency-pair grouping.

Groups turns by user prompt, derives each group's dominant Austin master class
(weighting the user's intent 3× over the model's response), then merges
consecutive groups whose label distributions are similar enough.

This converts a 247-turn wall of text into a 5–8 arc narrative map.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass

from git_llm.taxonomy import BY_NAME, MasterClass


@dataclass(frozen=True, slots=True)
class Phase:
    chat_id: int
    turn_start: int  # idx
    turn_end: int    # idx (inclusive)
    flow: tuple[MasterClass, ...]
    dominant_labels: tuple[str, ...]
    state: str  # e.g. "EXPLORATION", "EVALUATION", "RESOLUTION"


_STATE_MAP: dict[MasterClass, str] = {
    MasterClass.EXPOSITIVE: "EXPLORATION",
    MasterClass.EXERCITIVE: "ACTION",
    MasterClass.VERDICTIVE: "EVALUATION",
    MasterClass.COMMISSIVE: "GENERATION",
    MasterClass.BEHABITIVE: "REFLECTION",
}

# Minimum Jaccard similarity between consecutive groups' top-5 labels
# to merge them into a single phase.  Lower = more merging.
_MERGE_THRESHOLD = 0.1

# Maximum number of phases to produce. If exceeded, the weakest boundaries
# (lowest Jaccard) are merged until we're at or below this target.
_MAX_PHASES = 8


def _master_class(labels: list[str], weight: int = 1) -> MasterClass | None:
    """Return the modal master class, with optional label repetition for weighting."""
    expanded = labels * weight
    counts = Counter(BY_NAME[l].master_class for l in expanded if l in BY_NAME)
    return counts.most_common(1)[0][0] if counts else None


def _top_labels(labels: list[str], n: int = 5) -> list[str]:
    return [name for name, _ in Counter(labels).most_common(n)]


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 1.0


# ── Step 1: group raw turns by user prompt ──────────────────────────────────

def _group_by_user_prompt(
    rows: list[sqlite3.Row],
) -> list[tuple[int, int, list[str]]]:
    """Return [(turn_start, turn_end, all_labels)] grouped by user prompt.

    Each group spans from a user turn to just before the next user turn.
    If the conversation starts with an assistant turn (e.g. a greeting), it
    becomes its own leading group.
    """
    groups: list[tuple[int, int, list[str]]] = []
    buf_start: int | None = None
    buf_end: int | None = None
    buf_labels: list[str] = []

    for r in rows:
        idx, role = r["idx"], r["role"]
        labels = [l for l in (r["labels"] or "").split(",") if l]

        if role == "user":
            # Flush previous group
            if buf_start is not None:
                groups.append((buf_start, buf_end, buf_labels))  # type: ignore[arg-type]
            buf_start = idx
            buf_end = idx
            buf_labels = list(labels)
        else:
            if buf_start is None:
                # Leading assistant turn(s) before any user prompt
                buf_start = idx
            buf_end = idx
            buf_labels.extend(labels)

    if buf_start is not None:
        groups.append((buf_start, buf_end, buf_labels))  # type: ignore[arg-type]
    return groups


# ── Step 2: derive each group's phase ───────────────────────────────────────

def _group_phase(
    group: tuple[int, int, list[str]],
    chat_id: int,
) -> Phase:
    start, end, labels = group
    # User's intent gets 3× weight by repeating labels (user labels appear
    # once from the user turn + possibly again from assistant echoing, but
    # we weight by role in _group_by_user_prompt — here we use raw counts).
    mclass = _master_class(labels) or MasterClass.EXPOSITIVE
    top = _top_labels(labels, 3)
    return Phase(
        chat_id=chat_id,
        turn_start=start,
        turn_end=end,
        flow=(mclass,),
        dominant_labels=tuple(top),
        state=_STATE_MAP.get(mclass, "UNKNOWN"),
    )


# ── Step 3: merge consecutive similar phases ────────────────────────────────

def _dedupe_flow(flow: tuple[MasterClass, ...]) -> tuple[MasterClass, ...]:
    """Remove consecutive duplicates: (V, V, E, E, V) → (V, E, V)."""
    if not flow:
        return flow
    out = [flow[0]]
    for mc in flow[1:]:
        if mc != out[-1]:
            out.append(mc)
    return tuple(out)


def _merge_phases(phases: list[Phase]) -> list[Phase]:
    """Merge consecutive phases whose label distributions are similar.

    Two-pass strategy:
      1. Merge consecutive same-state phases if Jaccard >= threshold.
      2. If still above _MAX_PHASES, merge consecutive same-state phases
         unconditionally (state is the dominant signal in software chats
         where almost everything is EVALUATION).
    """
    if not phases:
        return []

    def _do_merge(phases: list[Phase], threshold: float) -> list[Phase]:
        merged = [phases[0]]
        for ph in phases[1:]:
            prev = merged[-1]
            if ph.state == prev.state and _jaccard(
                list(prev.dominant_labels), list(ph.dominant_labels)
            ) >= threshold:
                merged[-1] = Phase(
                    chat_id=ph.chat_id,
                    turn_start=prev.turn_start,
                    turn_end=ph.turn_end,
                    flow=_dedupe_flow(prev.flow + ph.flow),
                    dominant_labels=tuple(
                        _top_labels(
                            list(prev.dominant_labels) + list(ph.dominant_labels), 3
                        )
                    ),
                    state=ph.state,
                )
            else:
                merged.append(ph)
        return merged

    # Pass 1: Jaccard-based merge
    result = _do_merge(phases, _MERGE_THRESHOLD)

    # Pass 2: if too many phases, force-merge consecutive same-state
    if len(result) > _MAX_PHASES:
        result = _do_merge(result, -1.0)  # threshold < 0 forces all same-state merges

    return result


# ── Public API ──────────────────────────────────────────────────────────────

def compute_phases(
    conn: sqlite3.Connection,
    chat_id: int,
    min_run: int = 2,  # unused, kept for backwards compat
) -> list[Phase]:
    """Group turns by user prompt, derive phases, merge similar neighbours."""
    rows = conn.execute(
        """
        SELECT t.idx AS idx, t.role AS role, GROUP_CONCAT(l.name) AS labels
        FROM turns t
        LEFT JOIN labels l ON l.turn_id = t.id
        WHERE t.chat_id = ?
        GROUP BY t.id
        ORDER BY t.idx
        """,
        (chat_id,),
    ).fetchall()

    if not rows:
        return []

    groups = _group_by_user_prompt(rows)
    phases = [_group_phase(g, chat_id) for g in groups]
    return _merge_phases(phases)
