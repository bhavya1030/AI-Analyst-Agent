from backend.db import get_session, save_session


def test_session_memory_persists():
    session_id = "test_memory"
    save_session(
        session_id=session_id,
        last_query="test query",
        last_intent="analysis",
        last_chart_type="line",
        last_operation="analysis",
    )

    session = get_session(session_id)
    assert session is not None
    assert session.last_query == "test query"
    assert session.last_intent == "analysis"
    assert session.last_chart_type == "line"
    assert session.last_operation == "analysis"
