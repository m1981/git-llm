"""Tests for bulk pi-session import."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from git_llm import pi_bulk
from git_llm.pi_bulk import (
    BulkResult,
    bulk_import,
    discover_sessions,
    peek_session_header,
)


# ---------- Fixture builder ---------------------------------------------------

def _session_jsonl(session_id: str, cwd: str, ts_iso: str) -> str:
    """Minimal but valid pi session: 1 user turn + 1 assistant turn."""
    return (
        f'{{"type":"session","version":3,"id":"{session_id}","timestamp":"{ts_iso}","cwd":"{cwd}"}}\n'
        f'{{"type":"message","id":"u","parentId":null,"timestamp":"{ts_iso}",'
        '"message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n'
        f'{{"type":"message","id":"a","parentId":"u","timestamp":"{ts_iso}",'
        '"message":{"role":"assistant","content":[{"type":"text","text":"hello"}]}}\n'
    )


@pytest.fixture
def sessions_tree(tmp_path: Path) -> Path:
    """Build a synthetic ~/.pi/agent/sessions tree with 4 sessions over 2 repos."""
    root = tmp_path / "sessions"

    alpha = root / "--Users-demo-Projects-alpha--"
    beta = root / "--Users-demo-Projects-beta-repo--"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)

    (alpha / "2026-06-01T10-00-00-000Z_aaa.jsonl").write_text(
        _session_jsonl("sess-alpha-1", "/Users/demo/Projects/alpha", "2026-06-01T10:00:00Z")
    )
    (alpha / "2026-06-15T12-00-00-000Z_bbb.jsonl").write_text(
        _session_jsonl("sess-alpha-2", "/Users/demo/Projects/alpha", "2026-06-15T12:00:00Z")
    )
    (beta / "2026-06-10T09-00-00-000Z_ccc.jsonl").write_text(
        _session_jsonl("sess-beta-1", "/Users/demo/Projects/beta-repo", "2026-06-10T09:00:00Z")
    )
    (beta / "2026-06-20T14-00-00-000Z_ddd.jsonl").write_text(
        _session_jsonl("sess-beta-2", "/Users/demo/Projects/beta-repo", "2026-06-20T14:00:00Z")
    )

    # Decoy: a non-jsonl file and a non-session jsonl
    (alpha / "README.md").write_text("not a session")
    (alpha / "not-a-session.jsonl").write_text('{"role":"user","content":"hi"}\n')

    return root


# ---------- peek_session_header ----------------------------------------------

def test_peek_session_header_returns_dict(sessions_tree: Path):
    f = next((sessions_tree / "--Users-demo-Projects-alpha--").glob("*aaa*.jsonl"))
    h = peek_session_header(f)
    assert h is not None
    assert h["id"] == "sess-alpha-1"
    assert h["cwd"] == "/Users/demo/Projects/alpha"


def test_peek_session_header_rejects_non_pi(sessions_tree: Path):
    f = sessions_tree / "--Users-demo-Projects-alpha--" / "not-a-session.jsonl"
    assert peek_session_header(f) is None


def test_peek_handles_missing_file(tmp_path: Path):
    assert peek_session_header(tmp_path / "nope.jsonl") is None


# ---------- discover_sessions -------------------------------------------------

def test_discover_finds_all_sessions(sessions_tree: Path):
    refs = list(discover_sessions(sessions_tree))
    assert len(refs) == 4
    assert {r.session_id for r in refs} == {
        "sess-alpha-1", "sess-alpha-2", "sess-beta-1", "sess-beta-2"
    }


def test_discover_filters_by_repo_substring(sessions_tree: Path):
    refs = list(discover_sessions(sessions_tree, repo_patterns=["alpha"]))
    assert len(refs) == 2
    assert all(r.repo_name == "alpha" for r in refs)


def test_discover_filters_by_repo_glob(sessions_tree: Path):
    refs = list(discover_sessions(sessions_tree, repo_patterns=["beta-*"]))
    assert len(refs) == 2
    assert all("beta" in r.repo_name for r in refs)


def test_discover_filters_by_since(sessions_tree: Path):
    refs = list(discover_sessions(sessions_tree, since="2026-06-12"))
    ids = {r.session_id for r in refs}
    assert ids == {"sess-alpha-2", "sess-beta-2"}


def test_discover_filters_by_until(sessions_tree: Path):
    refs = list(discover_sessions(sessions_tree, until=date(2026, 6, 10)))
    ids = {r.session_id for r in refs}
    assert ids == {"sess-alpha-1", "sess-beta-1"}


def test_discover_filters_combined(sessions_tree: Path):
    refs = list(
        discover_sessions(
            sessions_tree,
            repo_patterns=["alpha"],
            since="2026-06-10",
            until="2026-06-30",
        )
    )
    ids = {r.session_id for r in refs}
    assert ids == {"sess-alpha-2"}


def test_discover_handles_missing_dir(tmp_path: Path):
    assert list(discover_sessions(tmp_path / "nope")) == []


# ---------- bulk_import -------------------------------------------------------

def test_bulk_import_writes_all(tmp_db, sessions_tree: Path):
    result = bulk_import(tmp_db, sessions_tree)
    assert isinstance(result, BulkResult)
    assert result.discovered == 4
    assert result.imported == 4
    assert result.skipped_dedup == 0
    assert result.failed == 0
    assert len(result.chat_ids) == 4

    n_chats = tmp_db.execute("SELECT COUNT(*) AS n FROM chats").fetchone()["n"]
    assert n_chats == 4


def test_bulk_import_is_idempotent(tmp_db, sessions_tree: Path):
    first = bulk_import(tmp_db, sessions_tree)
    second = bulk_import(tmp_db, sessions_tree)
    assert first.imported == 4
    assert second.imported == 0
    assert second.skipped_dedup == 4
    # No duplicate chats
    n = tmp_db.execute("SELECT COUNT(*) AS n FROM chats").fetchone()["n"]
    assert n == 4


def test_bulk_import_session_id_persisted(tmp_db, sessions_tree: Path):
    bulk_import(tmp_db, sessions_tree)
    rows = tmp_db.execute(
        "SELECT session_id FROM chats ORDER BY session_id"
    ).fetchall()
    assert [r["session_id"] for r in rows] == [
        "sess-alpha-1", "sess-alpha-2", "sess-beta-1", "sess-beta-2"
    ]


def test_bulk_import_respects_filters(tmp_db, sessions_tree: Path):
    result = bulk_import(
        tmp_db,
        sessions_tree,
        repo_patterns=["alpha"],
        since="2026-06-10",
    )
    assert result.imported == 1
    row = tmp_db.execute("SELECT session_id FROM chats").fetchone()
    assert row["session_id"] == "sess-alpha-2"


def test_bulk_import_dry_run_writes_nothing(tmp_db, sessions_tree: Path):
    result = bulk_import(tmp_db, sessions_tree, dry_run=True)
    assert result.discovered == 4
    assert result.imported == 0
    n = tmp_db.execute("SELECT COUNT(*) AS n FROM chats").fetchone()["n"]
    assert n == 0


# ---------- Migration ---------------------------------------------------------

def test_migration_adds_session_id_column(tmp_path: Path):
    """A DB created before session_id existed must be upgraded transparently."""
    import sqlite3

    db_path = tmp_path / "legacy.sqlite"
    legacy = sqlite3.connect(db_path)
    legacy.row_factory = sqlite3.Row
    legacy.executescript(
        """
        CREATE TABLE chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL,
            raw_path TEXT
        );
        INSERT INTO chats (title, source, created_at, raw_path)
        VALUES ('legacy', 'manual', '2026-01-01T00:00:00', '/x');
        """
    )
    legacy.commit()
    legacy.close()

    from git_llm import db as db_mod
    with db_mod.session(db_path) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(chats)")}
        assert "session_id" in cols
        # Old row still there.
        n = conn.execute("SELECT COUNT(*) AS n FROM chats").fetchone()["n"]
        assert n == 1


# ---------- Single-file dedup behavior at the ingest layer --------------------

def test_single_ingest_raises_on_duplicate(tmp_db, sessions_tree: Path):
    f = next(sessions_tree.rglob("*aaa*.jsonl"))
    from git_llm.ingest import ingest_file

    chat_id = ingest_file(tmp_db, f)
    assert chat_id > 0
    with pytest.raises(ValueError, match="already ingested"):
        ingest_file(tmp_db, f)


def test_single_ingest_skip_if_exists_returns_existing(tmp_db, sessions_tree: Path):
    f = next(sessions_tree.rglob("*aaa*.jsonl"))
    from git_llm.ingest import ingest_file

    first = ingest_file(tmp_db, f)
    second = ingest_file(tmp_db, f, skip_if_exists=True)
    assert first == second


# ---------- Default sessions dir constant -------------------------------------

def test_default_sessions_dir_is_under_home():
    assert pi_bulk.DEFAULT_SESSIONS_DIR == Path.home() / ".pi" / "agent" / "sessions"
