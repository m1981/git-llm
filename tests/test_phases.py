from git_llm.phases import compute_phases


def test_phases_produced(labeled_chat):
    conn, chat_id = labeled_chat
    ps = compute_phases(conn, chat_id)
    assert ps, "Expected at least one phase"
    # phases must be ordered and non-overlapping
    for a, b in zip(ps, ps[1:]):
        assert a.turn_end < b.turn_start
    # every phase has a state
    assert all(p.state for p in ps)
