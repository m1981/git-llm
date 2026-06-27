"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from git_llm import db as db_mod
from git_llm import ingest as ingest_mod
from git_llm import label as label_mod


FIXTURE = Path(__file__).parent / "fixtures" / "initial-conversation.md"


@pytest.fixture
def tmp_db(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    with db_mod.session(db_path) as conn:
        yield conn


@pytest.fixture
def ingested_chat(tmp_db):
    chat_id = ingest_mod.ingest_file(tmp_db, FIXTURE, title="initial")
    return tmp_db, chat_id


@pytest.fixture
def labeled_chat(ingested_chat):
    conn, chat_id = ingested_chat
    label_mod.label_chat(conn, chat_id, label_mod.StubLabeler())
    return conn, chat_id
