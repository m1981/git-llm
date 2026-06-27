from git_llm.search import search


def test_fts_search_finds_content(labeled_chat):
    conn, _ = labeled_chat
    # FTS5 returns turns containing the term anywhere; snippet may truncate it.
    hits = search(conn, text="Zettelkasten")
    assert hits, "Expected FTS to find at least one turn mentioning Zettelkasten"
    # Verify the full turn content actually contains the term.
    for h in hits:
        row = conn.execute(
            "SELECT content FROM turns WHERE chat_id=? AND idx=?", (h.chat_id, h.turn_idx)
        ).fetchone()
        assert "zettelkasten" in row["content"].lower()


def test_label_filter(labeled_chat):
    conn, _ = labeled_chat
    hits = search(conn, label="Inquiring")
    assert all("Inquiring" in h.labels for h in hits)


def test_combined_filter(labeled_chat):
    conn, _ = labeled_chat
    hits = search(conn, text="architecture", limit=5)
    assert len(hits) <= 5
