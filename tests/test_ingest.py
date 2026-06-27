from pathlib import Path

from git_llm.ingest import parse_markdown, ingest_file
from git_llm.taxonomy import Role


def test_parse_markdown_basic():
    text = "# user\nhello?\n\n# AI\nhi there.\n\n# user\nbye\n"
    turns = parse_markdown(text)
    assert [t[0] for t in turns] == [Role.USER, Role.ASSISTANT, Role.USER]
    assert turns[0][1] == "hello?"
    assert turns[1][1] == "hi there."


def test_parse_markdown_handles_model_heading():
    text = "# user\nq?\n# model\na.\n"
    turns = parse_markdown(text)
    assert turns[1][0] == Role.ASSISTANT


def test_ingest_real_conversation(tmp_db):
    fixture = Path(__file__).parent / "fixtures" / "initial-conversation.md"
    chat_id = ingest_file(tmp_db, fixture)
    n = tmp_db.execute("SELECT COUNT(*) AS n FROM turns WHERE chat_id=?", (chat_id,)).fetchone()["n"]
    assert n >= 6  # the doc has 4 user turns + 4 AI turns
