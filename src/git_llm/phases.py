"""
Macro-phase compression via adjacency-pair grouping.

Inspired by NLP's "adjacency pair" concept: certain label sequences naturally
co-occur (e.g. Seeking-Validation -> Validating). We collapse runs of turns
that share an Austin master-class into a single Phase, then label that phase
by the dominant flow.

This is what turns a 32-turn wall of text into a 5-arc map.
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


def _turn_master_class(labels: list[str]) -> MasterClass | None:
    """A turn's dominant master class = the modal class of its labels."""
    if not labels:
        return None
    counts = Counter(BY_NAME[l].master_class for l in labels if l in BY_NAME)
    return counts.most_common(1)[0][0] if counts else None


def compute_phases(conn: sqlite3.Connection, chat_id: int, min_run: int = 2) -> list[Phase]:
    """Group consecutive turns whose dominant master class is identical."""
    rows = conn.execute(
        """
        SELECT t.idx AS idx, GROUP_CONCAT(l.name) AS labels
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

    # Build per-turn master class series
    series: list[tuple[int, MasterClass | None, list[str]]] = []
    for r in rows:
        labels = (r["labels"] or "").split(",") if r["labels"] else []
        labels = [l for l in labels if l]
        series.append((r["idx"], _turn_master_class(labels), labels))

    # Collapse adjacent identical master classes into runs
    phases: list[Phase] = []
    if not series:
        return phases

    run_start = series[0][0]
    run_class = series[0][1]
    run_labels: list[str] = list(series[0][2])
    run_flow: list[MasterClass] = [run_class] if run_class else []

    def emit(end_idx: int) -> None:
        if run_class is None:
            return
        if end_idx - run_start + 1 < min_run and phases:
            # absorb a single-turn blip into the previous phase
            prev = phases[-1]
            phases[-1] = Phase(
                chat_id=chat_id,
                turn_start=prev.turn_start,
                turn_end=end_idx,
                flow=prev.flow + tuple(run_flow),
                dominant_labels=tuple(Counter(list(prev.dominant_labels) + run_labels).keys()),
                state=prev.state,
            )
            return
        top = [name for name, _ in Counter(run_labels).most_common(3)]
        phases.append(
            Phase(
                chat_id=chat_id,
                turn_start=run_start,
                turn_end=end_idx,
                flow=tuple(run_flow),
                dominant_labels=tuple(top),
                state=_STATE_MAP.get(run_class, "UNKNOWN"),
            )
        )

    for idx, mclass, labels in series[1:]:
        if mclass == run_class:
            run_labels.extend(labels)
        else:
            emit(idx - 1)
            run_start = idx
            run_class = mclass
            run_labels = list(labels)
            run_flow = [mclass] if mclass else []
    emit(series[-1][0])
    return phases
