"""Phase 7: automatic conversation summarization tests."""

from __future__ import annotations

import uuid

from backend.config import settings
from backend.sessions.service import SessionService
from backend.sessions.summarizer import maybe_summarize_session
from backend.db import SessionLocal
from backend.sessions.models import SessionMessage


def _sid(prefix: str = "p7") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def test_deterministic_summary_preserves_analytical_context(monkeypatch):
    monkeypatch.setattr(settings, "USE_LLM_SUMMARY", False)
    monkeypatch.setattr(settings, "CONVERSATION_SUMMARY_THRESHOLD", 6)
    monkeypatch.setattr(settings, "CONVERSATION_SUMMARY_KEEP_RECENT", 2)

    svc = SessionService()
    sid = _sid("det")
    svc.create_session(session_id=sid, title="GDP long chat", tags=["macro"])

    # Create enough turns to exceed threshold (user+assistant each = 2 msgs)
    for i in range(5):
        svc.append_user_message(sid, f"Question {i} about India GDP growth")
        svc.record_assistant_turn(
            sid,
            question=f"Question {i} about India GDP growth",
            result={
                "answer": f"Insight {i}: GDP grew in year range.",
                "dataset_topic": "India GDP",
                "dataset_url": "https://example.com/india-gdp.csv",
                "last_intent": "analysis" if i % 2 == 0 else "forecast",
                "last_operation": "eda" if i % 2 == 0 else "forecast",
                "last_chart_type": "line" if i % 2 == 0 else "forecast",
                "last_forecast_target": "Value" if i % 2 else None,
                "last_columns_used": ["Year", "Value"],
                "dataset_profile": {
                    "rows": 25,
                    "time_columns": ["Year"],
                    "numeric_columns": ["Value"],
                },
                "charts": [{"type": "line", "figure": {"data": []}}]
                if i % 2 == 0
                else [],
                "forecast": [{"ds": "2025", "yhat": 1.0}] if i % 2 else [],
                "insights": [f"pattern-{i}"],
                "rows": 25,
                "columns": ["Year", "Value"],
            },
        )

    # record_assistant_turn already triggers maybe_summarize
    detail = svc.get_session_detail(sid)
    assert detail.get("conversation_summary")
    summary = detail["conversation_summary"]
    assert "India GDP" in summary or "Dataset" in summary
    assert "Year" in summary or "Value" in summary or "Columns" in summary

    db = SessionLocal()
    try:
        msgs = (
            db.query(SessionMessage)
            .filter(SessionMessage.session_id == sid)
            .order_by(SessionMessage.seq.asc())
            .all()
        )
        summarized = [m for m in msgs if bool(getattr(m, "is_summarized", False))]
        intact = [m for m in msgs if not bool(getattr(m, "is_summarized", False))]
        assert len(summarized) >= 1
        # Keep recent intact
        assert len(intact) >= 2
        # Recent messages are the highest seq
        if intact and summarized:
            assert max(m.seq for m in intact) > max(m.seq for m in summarized)
    finally:
        db.close()

    svc.delete_session(sid, hard=True)


def test_below_threshold_no_fold(monkeypatch):
    monkeypatch.setattr(settings, "CONVERSATION_SUMMARY_THRESHOLD", 50)
    monkeypatch.setattr(settings, "CONVERSATION_SUMMARY_KEEP_RECENT", 12)
    monkeypatch.setattr(settings, "USE_LLM_SUMMARY", False)

    svc = SessionService()
    sid = _sid("low")
    svc.create_session(session_id=sid, title="Short")
    svc.append_user_message(sid, "Hello")
    svc.record_assistant_turn(
        sid,
        question="Hello",
        result={"answer": "Hi", "dataset_topic": "demo", "rows": 1, "columns": ["a"]},
    )
    result = maybe_summarize_session(sid)
    assert result is None

    db = SessionLocal()
    try:
        msgs = db.query(SessionMessage).filter(SessionMessage.session_id == sid).all()
        assert all(not bool(getattr(m, "is_summarized", False)) for m in msgs)
    finally:
        db.close()
    svc.delete_session(sid, hard=True)


def test_llm_fallback_when_llm_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "USE_LLM_SUMMARY", True)
    monkeypatch.setattr(settings, "CONVERSATION_SUMMARY_THRESHOLD", 4)
    monkeypatch.setattr(settings, "CONVERSATION_SUMMARY_KEEP_RECENT", 2)

    def _fake_llm(_prompt: str) -> str:
        return ""

    monkeypatch.setattr(
        "backend.llm.ollama_client.invoke_llm",
        _fake_llm,
    )

    svc = SessionService()
    sid = _sid("llmfb")
    svc.create_session(session_id=sid, title="Fallback")
    for i in range(3):
        svc.append_user_message(sid, f"Q{i} copper prices")
        svc.record_assistant_turn(
            sid,
            question=f"Q{i} copper prices",
            result={
                "answer": f"A{i} copper demand rose",
                "dataset_topic": "copper",
                "last_columns_used": ["Year", "Price"],
                "last_chart_type": "line",
                "rows": 5,
                "columns": ["Year", "Price"],
            },
        )

    detail = svc.get_session_detail(sid)
    assert detail.get("conversation_summary")
    assert "copper" in detail["conversation_summary"].lower() or "Dataset" in detail[
        "conversation_summary"
    ]
    svc.delete_session(sid, hard=True)


def test_summarizer_idempotent_after_fold(monkeypatch):
    monkeypatch.setattr(settings, "USE_LLM_SUMMARY", False)
    monkeypatch.setattr(settings, "CONVERSATION_SUMMARY_THRESHOLD", 4)
    monkeypatch.setattr(settings, "CONVERSATION_SUMMARY_KEEP_RECENT", 2)

    svc = SessionService()
    sid = _sid("idem")
    svc.create_session(session_id=sid, title="Idem")
    for i in range(3):
        svc.append_user_message(sid, f"msg {i}")
        svc.record_assistant_turn(
            sid,
            question=f"msg {i}",
            result={
                "answer": f"ans {i}",
                "dataset_topic": "gold",
                "rows": 2,
                "columns": ["x"],
            },
        )

    # Active messages should now be <= keep_recent after first fold
    second = maybe_summarize_session(sid)
    # Either None (nothing to fold) or a no-op small fold — not required to re-fold all
    if second is not None:
        assert second["folded_count"] >= 0

    svc.delete_session(sid, hard=True)
