from git_llm.label import StubLabeler, label_chat
from git_llm.models import Turn
from git_llm.taxonomy import BY_NAME, Role


def test_stub_labels_user_question_as_inquiring():
    t = Turn(chat_id=1, idx=0, role=Role.USER, content="What is Clean Architecture?")
    out = StubLabeler().label(t)
    names = {n for n, _ in out}
    assert "Inquiring" in names


def test_stub_labels_pivot():
    t = Turn(chat_id=1, idx=0, role=Role.USER, content="Actually, let's switch to Firebase.")
    out = StubLabeler().label(t)
    assert "Pivoting" in {n for n, _ in out}


def test_stub_labels_assistant_warning():
    t = Turn(
        chat_id=1,
        idx=0,
        role=Role.ASSISTANT,
        content="Warning: this is an anti-pattern that will exhaust your DB pool.",
    )
    out = StubLabeler().label(t)
    assert "Warning" in {n for n, _ in out}


def test_label_chat_persists(labeled_chat):
    conn, chat_id = labeled_chat
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM labels l "
        "JOIN turns t ON t.id = l.turn_id WHERE t.chat_id = ?",
        (chat_id,),
    ).fetchone()
    assert rows["n"] > 0


def test_master_class_is_consistent(labeled_chat):
    conn, _ = labeled_chat
    rows = conn.execute("SELECT name, master_class FROM labels").fetchall()
    for r in rows:
        assert BY_NAME[r["name"]].master_class.value == r["master_class"]
