"""Phase 3: session lifecycle, organization, list pagination/sort/filter."""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.sessions.router import router
from backend.sessions.service import SessionNotFoundError, SessionService


def _sid(prefix: str = "p3") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _svc() -> SessionService:
    return SessionService()


def test_rename_archive_restore():
    svc = _svc()
    sid = _sid("rar")
    svc.create_session(session_id=sid, title="Original")

    renamed = svc.rename_session(sid, "Renamed Title")
    assert renamed["title"] == "Renamed Title"

    archived = svc.archive_session(sid)
    assert archived["archived"] is True
    assert archived["status"] == "archived"

    # Soft-delete then restore
    svc.delete_session(sid, hard=False)
    restored = svc.restore_session(sid)
    assert restored["deleted"] is False
    assert restored["archived"] is False
    assert restored["status"] == "active"

    svc.delete_session(sid, hard=True)


def test_favorite_and_pin():
    svc = _svc()
    sid = _sid("fav")
    svc.create_session(session_id=sid, title="Pin me")

    fav = svc.set_favorite(sid, True)
    assert fav["favorite"] is True

    unfav = svc.set_favorite(sid, False)
    assert unfav["favorite"] is False

    pinned = svc.set_pinned(sid, True, pin_order=1)
    assert pinned["pinned"] is True
    assert pinned["pin_order"] == 1

    unpinned = svc.set_pinned(sid, False)
    assert unpinned["pinned"] is False
    assert unpinned["pin_order"] is None

    svc.delete_session(sid, hard=True)


def test_duplicate_copies_messages_and_artifacts():
    svc = _svc()
    sid = _sid("dup")
    svc.create_session(session_id=sid, title="Source chat")
    svc.append_user_message(sid, "What is GDP?")
    svc.record_assistant_turn(
        sid,
        question="What is GDP?",
        result={
            "answer": "Gross Domestic Product",
            "dataset_topic": "GDP",
            "dataset_profile": {"rows": 5},
            "charts": [{"type": "line", "figure": {"data": []}}],
            "insights": ["growth"],
            "rows": 5,
            "columns": ["Year", "Value"],
        },
    )

    dup = svc.duplicate_session(sid, title="Dup chat")
    assert dup["session_id"] != sid
    assert dup["title"] == "Dup chat"
    assert dup["source_session_id"] == sid

    detail = svc.get_session_detail(dup["session_id"])
    assert len(detail["chat_history"]) == 2
    assert len(detail["generated_charts"]) >= 1
    assert detail["dataset_topic"] == "GDP"

    svc.delete_session(sid, hard=True)
    svc.delete_session(dup["session_id"], hard=True)


def test_export_import_roundtrip():
    svc = _svc()
    sid = _sid("exp")
    svc.create_session(session_id=sid, title="Export me", tags=["macro"])
    svc.append_user_message(sid, "Hello")
    svc.record_assistant_turn(
        sid,
        question="Hello",
        result={"answer": "Hi there", "dataset_topic": "demo", "rows": 1, "columns": ["a"]},
    )

    bundle = svc.export_session(sid)
    assert bundle["format_version"] == "1.0"
    assert bundle["session"]["session_id"] == sid
    assert len(bundle["messages"]) == 2

    imported = svc.import_session(bundle, title="Imported copy")
    assert imported["imported"] is True
    assert imported["title"] == "Imported copy"
    assert imported["session_id"] != sid

    detail = svc.get_session_detail(imported["session_id"])
    assert len(detail["chat_history"]) == 2
    assert detail["chat_history"][1]["content"] == "Hi there"

    svc.delete_session(sid, hard=True)
    svc.delete_session(imported["session_id"], hard=True)


def test_recent_and_pagination_sort_filter():
    svc = _svc()
    uid = f"user-{uuid.uuid4().hex[:8]}"
    ids = []
    for i, title in enumerate(["Alpha GDP", "Beta Inflation", "Gamma Gold"]):
        sid = _sid(f"list{i}")
        ids.append(sid)
        svc.create_session(
            session_id=sid,
            title=title,
            user_id=uid,
            tags=["econ"] if i < 2 else ["commodities"],
        )
        # Touch last_activity via rename for ordering variety
        svc.rename_session(sid, title)

    svc.set_favorite(ids[0], True)
    svc.set_pinned(ids[2], True, pin_order=0)
    svc.archive_session(ids[1])

    # Pagination
    page1 = svc.list_sessions(user_id=uid, limit=2, offset=0, include_archived=True)
    assert page1["limit"] == 2
    assert page1["offset"] == 0
    assert page1["total"] >= 3
    assert len(page1["items"]) == 2
    # Pinned session should appear first
    assert page1["items"][0]["pinned"] is True

    page2 = svc.list_sessions(user_id=uid, limit=2, offset=2, include_archived=True)
    assert page2["offset"] == 2

    # Filter favorite
    favs = svc.list_sessions(user_id=uid, favorite=True, include_archived=True)
    assert all(item["favorite"] for item in favs["items"])
    assert any(item["session_id"] == ids[0] for item in favs["items"])

    # Filter archived
    archived = svc.list_sessions(user_id=uid, archived=True)
    assert all(item["archived"] for item in archived["items"])
    assert any(item["session_id"] == ids[1] for item in archived["items"])

    # Free-text q
    gold = svc.list_sessions(user_id=uid, q="Gold", include_archived=True)
    assert any("Gold" in item["title"] for item in gold["items"])

    # Tag filter
    econ = svc.list_sessions(user_id=uid, tag="econ", include_archived=True)
    assert all("econ" in item["tags"] for item in econ["items"])

    # Sort by title asc
    by_title = svc.list_sessions(
        user_id=uid,
        sort_by="title",
        order="asc",
        include_archived=True,
        pinned=False,  # ignore pin reordering for pure title sort check among unpinned
    )
    titles = [i["title"] for i in by_title["items"] if not i["pinned"]]
    assert titles == sorted(titles)

    recent = svc.recent_sessions(user_id=uid, limit=5)
    assert recent["total"] >= 1
    assert len(recent["items"]) <= 5
    # Archived excluded by default
    assert all(not i["archived"] for i in recent["items"])

    for sid in ids:
        svc.delete_session(sid, hard=True)


def test_phase3_rest_apis():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    sid = _sid("api")

    r = client.post("/sessions", json={"session_id": sid, "title": "API Session"})
    assert r.status_code == 201

    r = client.post(f"/sessions/{sid}/rename", json={"title": "API Renamed"})
    assert r.status_code == 200
    assert r.json()["title"] == "API Renamed"

    r = client.post(f"/sessions/{sid}/favorite", json={"favorite": True})
    assert r.status_code == 200
    assert r.json()["favorite"] is True

    r = client.post(f"/sessions/{sid}/pin", json={"pinned": True, "pin_order": 0})
    assert r.status_code == 200
    assert r.json()["pinned"] is True

    r = client.post(f"/sessions/{sid}/archive")
    assert r.status_code == 200
    assert r.json()["archived"] is True

    r = client.post(f"/sessions/{sid}/restore")
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    r = client.get(f"/sessions/{sid}/export")
    assert r.status_code == 200
    bundle = r.json()
    assert "messages" in bundle

    r = client.post(
        "/sessions/import",
        json={"bundle": bundle, "title": "From API Import"},
    )
    assert r.status_code == 201
    imported_id = r.json()["session_id"]

    r = client.post(f"/sessions/{sid}/duplicate", json={"title": "API Dup"})
    assert r.status_code == 201
    dup_id = r.json()["session_id"]

    r = client.get("/sessions/recent?limit=5")
    assert r.status_code == 200
    assert "items" in r.json()

    r = client.get(
        "/sessions?detail=true&limit=10&offset=0&sort_by=updated_at&order=desc&favorite=true"
    )
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body and "sort_by" in body

    for x in (sid, imported_id, dup_id):
        client.delete(f"/sessions/{x}?hard=true")


def test_restore_unknown_raises():
    svc = _svc()
    try:
        svc.restore_session("does-not-exist-" + uuid.uuid4().hex)
        assert False, "expected SessionNotFoundError"
    except SessionNotFoundError:
        pass
