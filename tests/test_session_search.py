"""Phase 4: SQLite FTS5 session search tests."""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.sessions.router import router
from backend.sessions.search import (
    build_match_query,
    fts5_available,
    rebuild_all_session_fts,
    search_sessions_fts,
)
from backend.sessions.service import SessionService


def _sid(prefix: str = "p4") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_build_match_query_escapes_and_and():
    q = build_match_query('gold GDP "weird')
    assert "AND" in q
    assert "gold" in q.lower() or '"gold"' in q.lower()


def test_fts_search_ranks_title_and_messages():
    svc = SessionService()
    uid = f"u-{uuid.uuid4().hex[:8]}"
    a = _sid("gold")
    b = _sid("gdp")
    svc.create_session(session_id=a, title="Gold price deep dive", user_id=uid, tags=["metals"])
    svc.create_session(session_id=b, title="India GDP trends", user_id=uid, tags=["macro"])

    svc.append_user_message(a, "Forecast bullion prices for next decade")
    svc.record_assistant_turn(
        a,
        question="Forecast bullion prices for next decade",
        result={
            "answer": "Gold is expected to rise with inflation hedge demand.",
            "dataset_topic": "gold",
            "rows": 10,
            "columns": ["Year", "Price"],
        },
    )
    svc.append_user_message(b, "Show GDP growth chart")
    svc.record_assistant_turn(
        b,
        question="Show GDP growth chart",
        result={
            "answer": "GDP grew steadily over twenty years.",
            "dataset_topic": "gdp",
            "rows": 20,
            "columns": ["Year", "Value"],
        },
    )

    rebuild_all_session_fts()

    results = svc.search_sessions("gold bullion", user_id=uid, limit=10)
    assert results["total"] >= 1
    assert results["engine"] in {"fts5", "like"}
    ids = [item["session_id"] for item in results["items"]]
    assert a in ids
    # Gold session should rank above GDP for this query when both match poorly
    top = results["items"][0]
    assert top["session_id"] == a
    assert "highlights" in top
    assert "snippet" in top
    # Highlights should mark something when FTS available
    joined = " ".join(str(v) for v in top["highlights"].values())
    if results["engine"] == "fts5":
        assert "<mark>" in joined or top["score"] > 0

    # Tag search
    tag_hits = svc.search_sessions("metals", user_id=uid)
    assert any(h["session_id"] == a for h in tag_hits["items"])

    # Pagination
    page = svc.search_sessions("growth OR gold OR gdp", user_id=uid, limit=1, offset=0)
    assert page["limit"] == 1
    assert len(page["items"]) <= 1

    svc.delete_session(a, hard=True)
    svc.delete_session(b, hard=True)


def test_search_excludes_deleted_by_default():
    svc = SessionService()
    sid = _sid("del")
    svc.create_session(session_id=sid, title="UniqueZebraSessionSearch")
    svc.append_user_message(sid, "UniqueZebra message content")
    rebuild_all_session_fts()

    hits = search_sessions_fts("UniqueZebra", include_deleted=False)
    assert any(h["session_id"] == sid for h in hits["items"])

    svc.delete_session(sid, hard=False)
    hits2 = search_sessions_fts("UniqueZebra", include_deleted=False)
    assert all(h["session_id"] != sid for h in hits2["items"])

    svc.delete_session(sid, hard=True)


def test_search_rest_api():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    svc = SessionService()
    sid = _sid("api")
    svc.create_session(session_id=sid, title="Copper commodities analysis")
    svc.append_user_message(sid, "Analyze copper supply chain")
    svc.record_assistant_turn(
        sid,
        question="Analyze copper supply chain",
        result={"answer": "Copper demand is rising with EV production.", "rows": 3, "columns": ["x"]},
    )
    rebuild_all_session_fts()

    r = client.get("/sessions/search", params={"q": "copper EV", "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "copper EV"
    assert "items" in body
    assert "total" in body
    assert body["engine"] in {"fts5", "like", "none"}
    if body["items"]:
        hit = body["items"][0]
        assert "score" in hit and "highlights" in hit and "rank" in hit

    # Empty-ish validation: min_length=1 enforced by FastAPI
    r2 = client.get("/sessions/search", params={"q": ""})
    assert r2.status_code == 422

    svc.delete_session(sid, hard=True)


def test_fts5_probe_does_not_crash():
    # Just ensure availability check is stable
    assert isinstance(fts5_available(), bool)
