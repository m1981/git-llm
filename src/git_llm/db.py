"""SQLite schema + connection. FTS5 for full-text recall across all chats."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path.home() / ".git-llm" / "chatdb.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'manual',
    created_at  TEXT NOT NULL,
    raw_path    TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    idx             INTEGER NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content         TEXT NOT NULL,
    token_estimate  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (chat_id, idx)
);

CREATE TABLE IF NOT EXISTS labels (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id       INTEGER NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    master_class  TEXT NOT NULL,
    confidence    REAL NOT NULL DEFAULT 1.0,
    labeler       TEXT NOT NULL DEFAULT 'manual',
    UNIQUE (turn_id, name, labeler)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('knowledge','adr')),
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    zk_id       TEXT NOT NULL UNIQUE,
    turn_start  INTEGER NOT NULL,
    turn_end    INTEGER NOT NULL,
    labels      TEXT NOT NULL DEFAULT '',  -- comma-separated for quick filter
    file_path   TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_links (
    artifact_id    INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    linked_zk_id   TEXT NOT NULL,
    PRIMARY KEY (artifact_id, linked_zk_id)
);

-- FTS5 mirror over turn content (cross-chat recall).
CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
    content,
    content='turns',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Keep FTS in sync via triggers.
CREATE TRIGGER IF NOT EXISTS turns_fts_ai AFTER INSERT ON turns BEGIN
    INSERT INTO turns_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS turns_fts_ad AFTER DELETE ON turns BEGIN
    INSERT INTO turns_fts(turns_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS turns_fts_au AFTER UPDATE ON turns BEGIN
    INSERT INTO turns_fts(turns_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO turns_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE INDEX IF NOT EXISTS idx_turns_chat ON turns(chat_id, idx);
CREATE INDEX IF NOT EXISTS idx_labels_name ON labels(name);
CREATE INDEX IF NOT EXISTS idx_labels_turn ON labels(turn_id);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def session(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        init_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
