"""Phase 1: core session persistence tests."""

from __future__ import annotations

import uuid

from backend.sessions.service import SessionNotFoundError, SessionService, get_session_service


def _sid(prefix: str = "p1") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_create_list_get_update_delete_session():
    svc = SessionService()
    sid = _sid("crud")

    created = svc.create_session(session_id=sid, title="GDP analysis", tags=["macro"])
    assert created["session_id"] == sid
    assert created["title"] == "GDP analysis"
    assert "macro" in created["tags"]

    listed = svc.list_sessions(limit=200)
    ids = {item["session_id"] for item in listed["items"]}
    assert sid in ids

    detail = svc.get_session_detail(sid)
    assert detail["session_id"] == sid
    assert detail["chat_history"] == []
    assert detail["title"] == "GDP analysis"

    updated = svc.update_session(sid, title="Renamed session", favorite=True)
    assert updated["title"] == "Renamed session"
    assert updated["favorite"] is True

    deleted = svc.delete_session(sid, hard=False)
    assert deleted["deleted"] is True

    try:
        svc.get_session_detail(sid)
        assert False, "expected SessionNotFoundError"
    except SessionNotFoundError:
        pass

    # hard delete cleans up
    svc.delete_session(sid, hard=True)


def test_ask_turn_persists_messages_and_artifacts():
    svc = SessionService()
    sid = _sid("turn")
    svc.ensure_session(sid)

    user = svc.append_user_message(sid, "Forecast India GDP for 10 years")
    assert user["role"] == "user"
    assert user["seq"] == 1

    fake_result = {
        "answer": "GDP is expected to grow steadily.",
        "dataset_topic": "India GDP",
        "dataset_url": "https://example.com/gdp.csv",
        "dataset_profile": {"rows": 100, "columns": ["Year", "Value"]},
        "last_columns_used": ["Year", "Value"],
        "last_chart_type": "line",
        "last_intent": "forecast",
        "last_operation": "forecast",
        "last_forecast_target": "Value",
        "charts": [
            {
                "id": "c1",
                "type": "line",
                "figure": {"data": [{"x": [1, 2], "y": [3, 4]}], "layout": {"title": "GDP"}},
            }
        ],
        "forecast": [{"Year": 2025, "Value": 1.2}],
        "forecast_chart": {"data": [], "layout": {}},
        "insights": ["Upward trend"],
        "hypotheses": ["Growth continues"],
        "detected_patterns": ["trend"],
        "recommended_next_steps": ["Compare with peers"],
        "chart_explanation": "Line chart of GDP over time",
        "rows": 100,
        "columns": ["Year", "Value"],
    }

    turn = svc.record_assistant_turn(sid, question="Forecast India GDP for 10 years", result=fake_result)
    assert turn["message_id"]
    assert len(turn["artifact_ids"]) >= 1

    detail = svc.get_session_detail(sid)
    assert detail["message_count"] == 2
    assert len(detail["chat_history"]) == 2
    assert detail["chat_history"][0]["role"] == "user"
    assert detail["chat_history"][1]["role"] == "assistant"
    assert "grow steadily" in detail["chat_history"][1]["content"]

    # Restore without recomputation
    assert detail["dataset_topic"] == "India GDP"
    assert detail["dataset_url"] == "https://example.com/gdp.csv"
    assert len(detail["generated_charts"]) >= 1
    assert len(detail["forecast_results"]) >= 1
    assert len(detail["eda_outputs"]) >= 1
    assert len(detail["analysis_results"]) >= 1
    assert detail["eda_summary"].get("rows") == 100
    assert detail["last_insight"]



    svc.delete_session(sid, hard=True)



def test_list_session_ids_backward_compatible():
    svc = get_session_service()
    sid = _sid("ids")
    svc.create_session(session_id=sid, title="Compat")
    ids = svc.list_session_ids()
    assert isinstance(ids, list)
    assert sid in ids
    assert all(isinstance(x, str) for x in ids)
    svc.delete_session(sid, hard=True)


def test_dataframe_stripped_from_artifacts():
    import pandas as pd

    svc = SessionService()
    sid = _sid("df")
    svc.ensure_session(sid)
    svc.append_user_message(sid, "analyze")

    result = {
        "answer": "ok",
        "data": pd.DataFrame({"a": [1, 2, 3]}),
        "dataset_profile": {"cols": 1},
        "charts": [{"type": "bar", "figure": {"data": []}}],
        "rows": 3,
        "columns": ["a"],
    }
    turn = svc.record_assistant_turn(sid, question="analyze", result=result)
    detail = svc.get_session_detail(sid)
    # Should not have exploded into thousands of row records
    assert detail["chat_history"][-1]["content"] == "ok"
    assert len(detail["generated_charts"]) == 1
    assert turn["artifact_ids"]
    svc.delete_session(sid, hard=True)
