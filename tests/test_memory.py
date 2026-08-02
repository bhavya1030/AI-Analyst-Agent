"""Verify session state persists via SessionService (Phase 2: no legacy DB functions)."""
from __future__ import annotations

import uuid

from backend.sessions.service import SessionService


def _sid() -> str:
    return f"test_memory_{uuid.uuid4().hex[:12]}"


def test_session_memory_persists():
    svc = SessionService()
    sid = _sid()
    svc.ensure_session(sid)
    svc.append_user_message(sid, "test query")
    svc.record_assistant_turn(
        sid,
        question="test query",
        result={
            "answer": "ok",
            "last_intent": "analysis",
            "last_chart_type": "line",
            "last_operation": "analysis",
        },
    )
    detail = svc.get_session_detail(sid)
    assert detail["last_query"] == "test query"
    assert detail["last_intent"] == "analysis"
    assert detail["last_chart_type"] == "line"
    assert detail["last_operation"] == "analysis"
    svc.delete_session(sid, hard=True)
