"""
Bulk-import every pi.dev agent session under `~/.pi/agent/sessions/`.

Pi stores sessions as:

    ~/.pi/agent/sessions/
        --Users-michal-PycharmProjects-git-llm--/
            2026-06-27T15-01-05-061Z_<uuid>.jsonl
            2026-06-28T09-12-22-000Z_<uuid>.jsonl
        --Users-michal-PycharmProjects-other-repo--/
            ...

The directory name is the user's `cwd` with `/` replaced by `-` and wrapped in
`--...--`. That encoding is lossy when the path itself contains `-`, so we do
NOT try to decode it back. Instead, every session file is authoritative about
its own working directory because the first line is:

    {"type":"session","cwd":"/Users/.../repo","id":"...","timestamp":"...","version":3}

We `peek_session_header` to read that line cheaply, filter by repo basename
and date, then route every accepted file through `ingest_file(skip_if_exists=True)`.
Dedup is by `session_id` (unique partial index on `chats.session_id`), so re-runs
of `import-pi --all` are idempotent.
"""

from __future__ import annotations

import fnmatch
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator

from git_llm.ingest import ingest_file

DEFAULT_SESSIONS_DIR = Path.home() / ".pi" / "agent" / "sessions"

# Filename prefix: 2026-06-27T15-01-05-061Z_<uuid>.jsonl
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T")


@dataclass(slots=True)
class SessionRef:
    """One candidate session file with its header metadata."""
    path: Path
    cwd: str | None
    session_id: str | None
    timestamp: datetime | None
    repo_dir: str  # name of the parent dir, e.g. "--Users-michal-PycharmProjects-git-llm--"

    @property
    def repo_name(self) -> str:
        """Best-effort short name. Prefers the session's `cwd` basename."""
        if self.cwd:
            return Path(self.cwd).name
        # fall back to stripping the `--...--` wrapper and using the last segment
        bare = self.repo_dir.strip("-")
        return bare.rsplit("-", 1)[-1] if bare else self.repo_dir


@dataclass(slots=True)
class BulkResult:
    discovered: int = 0
    imported: int = 0
    skipped_dedup: int = 0
    failed: int = 0
    failures: list[tuple[Path, str]] = field(default_factory=list)
    chat_ids: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def peek_session_header(path: Path) -> dict | None:
    """Read just the first line of a JSONL file and parse it as JSON."""
    try:
        with path.open("r", encoding="utf-8") as f:
            first = f.readline()
        if not first.strip():
            return None
        d = json.loads(first)
        return d if isinstance(d, dict) and d.get("type") == "session" else None
    except (OSError, json.JSONDecodeError):
        return None


def _filename_date(path: Path) -> date | None:
    m = _TS_RE.match(path.name)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _parse_iso_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        # Python <3.11 cannot parse trailing `Z`; just normalize.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def discover_sessions(
    sessions_dir: Path,
    *,
    repo_patterns: Iterable[str] | None = None,
    since: date | str | None = None,
    until: date | str | None = None,
) -> Iterator[SessionRef]:
    """Yield session files matching repo+date filters, with their headers."""
    if not sessions_dir.exists():
        return

    since_d = _coerce_date(since)
    until_d = _coerce_date(until)
    patterns = [p.strip() for p in repo_patterns if p.strip()] if repo_patterns else None

    for repo_dir in sorted(p for p in sessions_dir.iterdir() if p.is_dir()):
        for f in sorted(repo_dir.glob("*.jsonl")):
            # Cheap date filter from filename before opening the file.
            fdate = _filename_date(f)
            if since_d and fdate and fdate < since_d:
                continue
            if until_d and fdate and fdate > until_d:
                continue

            header = peek_session_header(f)
            if header is None:
                continue  # not a pi session

            ref = SessionRef(
                path=f,
                cwd=header.get("cwd"),
                session_id=header.get("id"),
                timestamp=_parse_iso_dt(header.get("timestamp")),
                repo_dir=repo_dir.name,
            )

            if patterns and not _matches_repo(ref, patterns):
                continue

            yield ref


def _coerce_date(v: date | str | None) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(v)


def _matches_repo(ref: SessionRef, patterns: list[str]) -> bool:
    candidates = {ref.repo_name, ref.repo_dir}
    if ref.cwd:
        candidates.add(ref.cwd)
    for pat in patterns:
        # plain substring OR fnmatch glob — both work, both intuitive.
        for c in candidates:
            if fnmatch.fnmatch(c, pat) or pat in c:
                return True
    return False


# ---------------------------------------------------------------------------
# Bulk runner
# ---------------------------------------------------------------------------

def bulk_import(
    conn: sqlite3.Connection,
    sessions_dir: Path | None = None,
    *,
    repo_patterns: Iterable[str] | None = None,
    since: date | str | None = None,
    until: date | str | None = None,
    dry_run: bool = False,
) -> BulkResult:
    """Discover + ingest every matching session. Idempotent by `session_id`."""
    sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR
    result = BulkResult()

    for ref in discover_sessions(
        sessions_dir,
        repo_patterns=repo_patterns,
        since=since,
        until=until,
    ):
        result.discovered += 1

        if dry_run:
            continue

        # Dedup pre-check (cheap) so we report skipped vs. imported correctly.
        if ref.session_id:
            row = conn.execute(
                "SELECT id FROM chats WHERE session_id = ?", (ref.session_id,)
            ).fetchone()
            if row:
                result.skipped_dedup += 1
                continue

        try:
            chat_id = ingest_file(conn, ref.path, skip_if_exists=True)
            result.imported += 1
            result.chat_ids.append(chat_id)
        except Exception as e:  # noqa: BLE001 — bulk runner must not crash mid-flight
            result.failed += 1
            result.failures.append((ref.path, str(e)))

    return result
