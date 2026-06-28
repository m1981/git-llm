"""
Extract Zettelkasten artifacts from labeled chats.

Two artifact kinds:
    - knowledge: triggered by Educational / Reflective / (Pragmatic+Warning)
                 turns. Atomic concept notes.
    - adr:       triggered by sequences matching ADR_TRIGGER_SEQUENCES, e.g.
                 Pivoting -> Pragmatic -> Synthesizing.

Each artifact is a Markdown file with YAML frontmatter (Obsidian-compatible).
A unique Zettel ID (YYYYMMDDHHMM-slug) ensures stable backlinks.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml
from slugify import slugify

import re as _re

from git_llm.taxonomy import ADR_TRIGGER_SEQUENCES, KNOWLEDGE_TRIGGERS

# Patterns for content that should NOT be promoted to knowledge notes.
_THINKING_RE = _re.compile(r"^\[thinking]\s*\n", _re.IGNORECASE)
_TOOL_USE_RE = _re.compile(r"\[tool_use:\w+]")
_MIN_CONTENT_LEN = 200  # chars of real content required after stripping


@dataclass(slots=True)
class ExtractedArtifact:
    kind: str
    title: str
    body: str
    zk_id: str
    turn_start: int
    turn_end: int
    labels: list[str]
    file_path: Path | None = None
    related: list[str] = None  # zk_ids of related artifacts (backlinks)

    def __post_init__(self):
        if self.related is None:
            self.related = []


def _labels_for_chat(conn: sqlite3.Connection, chat_id: int) -> dict[int, list[str]]:
    rows = conn.execute(
        """
        SELECT t.idx AS idx, l.name AS name
        FROM turns t
        JOIN labels l ON l.turn_id = t.id
        WHERE t.chat_id = ?
        ORDER BY t.idx
        """,
        (chat_id,),
    ).fetchall()
    out: dict[int, list[str]] = defaultdict(list)
    for r in rows:
        out[r["idx"]].append(r["name"])
    return out


def _turn_content(conn: sqlite3.Connection, chat_id: int, idx: int) -> str:
    row = conn.execute(
        "SELECT content FROM turns WHERE chat_id = ? AND idx = ?",
        (chat_id, idx),
    ).fetchone()
    return row["content"] if row else ""


def _zk_id(title: str, when: datetime | None = None) -> str:
    when = when or datetime.utcnow()
    return f"{when.strftime('%Y%m%d%H%M%S')}-{slugify(title)[:60]}"


def _matches_trigger(labels: list[str], trigger: tuple[str, ...]) -> bool:
    return any(name in trigger for name in labels)


def _derive_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if 10 <= len(stripped) <= 80:
            return stripped
    return fallback


def _real_content_length(text: str) -> int:
    """Return the length of 'real' content after stripping thinking blocks
    and tool-use markers. Used to decide whether a turn is worth extracting."""
    stripped = text.strip()
    # Strip leading [thinking] block (may span multiple lines)
    stripped = _THINKING_RE.sub("", stripped)
    # Remove [tool_use:...] inline markers
    stripped = _TOOL_USE_RE.sub("", stripped)
    return len(stripped.strip())


def _is_knowledge_worthy(content: str, labels: list[str] | None = None) -> bool:
    """Return True if this turn has enough real content to be a knowledge note.

    Thinking blocks are only promoted if they carry a strong knowledge trigger
    (Educational, or Pragmatic+Warning).  Otherwise they are raw reasoning
    traces that would dilute the zettel pool.
    """
    real_len = _real_content_length(content)
    if real_len < _MIN_CONTENT_LEN:
        return False
    # Thinking blocks without a strong knowledge label are noise.
    # Educational alone is too weak — the stub labeler assigns it to any
    # thinking block containing words like "concept" or "principle".
    # Synthesizing (multi-concept integration), Pragmatic+Warning (trade-off
    # reasoning), and Reflective (retrospection) are strong enough signals
    # that a thinking block contains durable knowledge.
    if _THINKING_RE.match(content.strip()) and labels:
        has_strong_trigger = (
            "Synthesizing" in labels
            or ("Pragmatic" in labels and "Warning" in labels)
            or "Reflective" in labels
        )
        if not has_strong_trigger:
            return False
    return True


def extract_knowledge(
    conn: sqlite3.Connection, chat_id: int
) -> list[ExtractedArtifact]:
    """One knowledge note per qualifying turn."""
    turn_labels = _labels_for_chat(conn, chat_id)
    artifacts: list[ExtractedArtifact] = []
    seen_zk: set[str] = set()

    for idx in sorted(turn_labels):
        labels = turn_labels[idx]
        if not any(_matches_trigger(labels, trig) for trig in KNOWLEDGE_TRIGGERS):
            continue
        content = _turn_content(conn, chat_id, idx)
        if not _is_knowledge_worthy(content, labels):
            continue  # skip thinking blocks without strong triggers and short turns
        title = _derive_title(content, f"Knowledge from turn {idx}")
        zk_id = _zk_id(title, datetime.utcnow())
        # disambiguate within same second
        suffix = 0
        base = zk_id
        while zk_id in seen_zk:
            suffix += 1
            zk_id = f"{base}-{suffix}"
        seen_zk.add(zk_id)
        artifacts.append(
            ExtractedArtifact(
                kind="knowledge",
                title=title,
                body=content,
                zk_id=zk_id,
                turn_start=idx,
                turn_end=idx,
                labels=labels,
            )
        )
    return artifacts


def extract_adrs(conn: sqlite3.Connection, chat_id: int) -> list[ExtractedArtifact]:
    """Detect ADR-worthy sequences and emit a single note per match."""
    turn_labels = _labels_for_chat(conn, chat_id)
    indices = sorted(turn_labels)
    artifacts: list[ExtractedArtifact] = []
    seen_zk: set[str] = set()

    for sequence in ADR_TRIGGER_SEQUENCES:
        i = 0
        while i <= len(indices) - len(sequence):
            window = indices[i : i + len(sequence)]
            if all(
                _matches_trigger(turn_labels[window[k]], sequence[k])
                for k in range(len(sequence))
            ):
                # Merge content across the window
                joined = "\n\n---\n\n".join(
                    _turn_content(conn, chat_id, j) for j in window
                )
                title = _derive_title(joined, f"ADR from turns {window[0]}-{window[-1]}")
                zk_id = _zk_id("ADR-" + title, datetime.utcnow())
                base = zk_id
                suffix = 0
                while zk_id in seen_zk:
                    suffix += 1
                    zk_id = f"{base}-{suffix}"
                seen_zk.add(zk_id)
                merged_labels: list[str] = []
                for j in window:
                    merged_labels.extend(turn_labels[j])
                artifacts.append(
                    ExtractedArtifact(
                        kind="adr",
                        title=title,
                        body=joined,
                        zk_id=zk_id,
                        turn_start=window[0],
                        turn_end=window[-1],
                        labels=sorted(set(merged_labels)),
                    )
                )
                i += len(sequence)  # consume window
            else:
                i += 1
    return artifacts


def _resolve_backlinks(artifacts: list[ExtractedArtifact], min_shared: int = 2) -> int:
    """Add bidirectional related: links between zettels sharing ≥min_shared labels.

    Returns the number of links created.
    """
    n_links = 0
    for i, a in enumerate(artifacts):
        for j in range(i + 1, len(artifacts)):
            b = artifacts[j]
            shared = set(a.labels) & set(b.labels)
            if len(shared) >= min_shared:
                a.related.append(b.zk_id)
                b.related.append(a.zk_id)
                n_links += 1
    return n_links


def render_markdown(artifact: ExtractedArtifact, chat_id: int) -> str:
    frontmatter = {
        "id": artifact.zk_id,
        "kind": artifact.kind,
        "created": datetime.utcnow().date().isoformat(),
        "source_chat": chat_id,
        "source_turns": list(range(artifact.turn_start, artifact.turn_end + 1)),
        "labels": sorted(set(artifact.labels)),
    }
    if artifact.related:
        frontmatter["related"] = sorted(set(artifact.related))
    fm = yaml.safe_dump(frontmatter, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n# {artifact.title}\n\n{artifact.body}\n"


def write_artifacts(
    conn: sqlite3.Connection,
    chat_id: int,
    artifacts: list[ExtractedArtifact],
    out_dir: Path,
) -> list[ExtractedArtifact]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for art in artifacts:
        sub = out_dir / ("adrs" if art.kind == "adr" else "notes")
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / f"{art.zk_id}.md"
        path.write_text(render_markdown(art, chat_id), encoding="utf-8")
        art.file_path = path
        conn.execute(
            "INSERT OR IGNORE INTO artifacts "
            "(chat_id, kind, title, body, zk_id, turn_start, turn_end, labels, file_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chat_id,
                art.kind,
                art.title,
                art.body,
                art.zk_id,
                art.turn_start,
                art.turn_end,
                ",".join(sorted(set(art.labels))),
                str(path.resolve()),
                datetime.utcnow().isoformat(),
            ),
        )
        # Persist backlinks to artifact_links table
        for related_id in art.related:
            conn.execute(
                "INSERT OR IGNORE INTO artifact_links (artifact_id, linked_zk_id) "
                "VALUES ((SELECT id FROM artifacts WHERE zk_id = ?), ?)",
                (art.zk_id, related_id),
            )
    conn.commit()
    return artifacts


def extract_all(
    conn: sqlite3.Connection, chat_id: int, out_dir: Path
) -> list[ExtractedArtifact]:
    artifacts = extract_knowledge(conn, chat_id) + extract_adrs(conn, chat_id)
    _resolve_backlinks(artifacts)
    return write_artifacts(conn, chat_id, artifacts, out_dir)
