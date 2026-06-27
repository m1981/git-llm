from pathlib import Path

import yaml

from git_llm.extract import extract_all


def test_extract_writes_files(labeled_chat, tmp_path: Path):
    conn, chat_id = labeled_chat
    arts = extract_all(conn, chat_id, tmp_path / "zettel")
    assert arts, "Expected at least one artifact from the fixture chat"
    for art in arts:
        assert art.file_path and art.file_path.exists()
        content = art.file_path.read_text()
        # YAML frontmatter present and parseable
        assert content.startswith("---\n")
        _, fm, _body = content.split("---\n", 2)
        meta = yaml.safe_load(fm)
        assert meta["id"] == art.zk_id
        assert meta["kind"] in ("knowledge", "adr")
        assert meta["source_chat"] == chat_id


def test_extract_registers_in_db(labeled_chat, tmp_path: Path):
    conn, chat_id = labeled_chat
    extract_all(conn, chat_id, tmp_path / "zettel")
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM artifacts WHERE chat_id=?", (chat_id,)
    ).fetchone()["n"]
    assert n > 0
