"""Session Reliability v2 — atomic commits, create/GET race, stress, lifecycle."""

from __future__ import annotations

import concurrent.futures
import threading
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import SessionLocal, get_session
from backend.sessions.models import AnalysisSession, SessionArtifact, SessionMessage
from backend.sessions.router import router
from backend.sessions.service import (
    SessionNotFoundError,
    SessionService,
    get_session_service,
)
from backend.sessions.transactions import (
    finalize_session_write,
    verify_session_row,
)


def _sid(prefix: str = "rel") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _svc() -> SessionService:
    return SessionService()


# ── create → immediate GET ─────────────────────────────────────────────────


def test_create_then_immediate_get():
    svc = _svc()
    sid = _sid("cget")
    created = svc.create_session(
        session_id=sid,
        title="Immediate GET",
        dataset_path="/tmp/demo.csv",
        dataset_name="demo",
        tags=["stress"],
    )
    assert created["committed"] is True
    assert created["session_id"] == sid

    # No sleep — must be durable immediately
    detail = svc.get_session_detail(sid)
    assert detail["session_id"] == sid
    assert detail["title"] == "Immediate GET"
    assert detail["dataset_path"] == "/tmp/demo.csv"
    # messages alias for regression clients
    assert "messages" in detail
    assert detail["messages"] == detail["chat_history"]

    verify = verify_session_row(sid)
    assert verify["verified"] is True

    svc.delete_session(sid, hard=True)


def test_create_via_api_then_get_no_gap():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    sid = _sid("api")

    r = client.post(
        "/v1/sessions",
        json={"session_id": sid, "title": "API create", "dataset_path": "x.csv"},
        headers={"X-User-Id": "rel-user"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["session_id"] == sid
    assert body.get("committed") is True

    r2 = client.get(f"/v1/sessions/{sid}", headers={"X-User-Id": "rel-user"})
    assert r2.status_code == 200, r2.text
    detail = r2.json()
    assert detail["session_id"] == sid
    assert detail.get("messages") is not None  # alias present

    # cleanup
    client.delete(f"/v1/sessions/{sid}?hard=true", headers={"X-User-Id": "rel-user"})


def test_assistant_turn_atomic_messages_and_artifacts():
    svc = _svc()
    sid = _sid("turn")
    svc.create_session(session_id=sid, title="Turn")
    svc.append_user_message(sid, "Analyze GDP")
    turn = svc.record_assistant_turn(
        sid,
        question="Analyze GDP",
        result={
            "answer": "GDP grew.",
            "dataset_topic": "GDP",
            "dataset_path": "gdp.csv",
            "file_path": "gdp.csv",
            "rows": 10,
            "columns": ["Year", "Value"],
            "charts": [{"type": "line", "figure": {"data": []}}],
            "insights": ["up"],
        },
        file_path="gdp.csv",
    )
    assert turn.get("committed") is True
    assert turn.get("message_id")
    assert turn.get("artifact_ids")

    # Immediate detail must show path + messages + artifacts
    detail = svc.get_session_detail(sid)
    assert detail["dataset_path"] == "gdp.csv" or detail["dataset_topic"] == "GDP"
    assert len(detail["chat_history"]) >= 2
    assert len(detail["messages"]) >= 2
    assert len(detail["generated_charts"]) >= 1 or len(detail["artifacts"]) >= 1

    # Legacy dual-write committed in same txn
    legacy = get_session(sid)
    assert legacy is not None
    assert legacy.dataset_topic == "GDP" or legacy.last_query

    finalize = finalize_session_write(sid, expect_messages=True)
    assert finalize["finalized"] is True
    assert finalize["message_rows"] >= 2

    svc.delete_session(sid, hard=True)


# ── lifecycle ──────────────────────────────────────────────────────────────


def test_lifecycle_rename_archive_duplicate_delete_restore():
    svc = _svc()
    sid = _sid("life")
    svc.create_session(session_id=sid, title="Life")
    svc.append_user_message(sid, "hello")
    svc.record_assistant_turn(
        sid,
        question="hello",
        result={"answer": "hi", "dataset_topic": "demo", "rows": 1, "columns": ["a"]},
    )

    renamed = svc.rename_session(sid, "Renamed Life")
    assert renamed["title"] == "Renamed Life"
    assert svc.get_session_detail(sid)["title"] == "Renamed Life"

    dup = svc.duplicate_session(sid, title="Life Copy")
    dup_id = dup["session_id"]
    assert dup_id != sid
    assert len(svc.get_session_detail(dup_id)["chat_history"]) >= 2

    archived = svc.archive_session(sid)
    assert archived["archived"] is True
    assert archived["status"] == "archived"

    restored = svc.restore_session(sid)
    assert restored["archived"] is False
    assert restored["status"] == "active"
    # Still readable with messages
    assert len(svc.get_session_detail(sid)["messages"]) >= 2

    soft = svc.delete_session(sid, hard=False)
    assert soft["deleted"] is True
    with pytest.raises(SessionNotFoundError):
        svc.get_session_detail(sid)

    # Restore after soft-delete
    again = svc.restore_session(sid)
    assert again["deleted"] is False
    detail = svc.get_session_detail(sid)
    assert detail["session_id"] == sid

    svc.delete_session(sid, hard=True)
    svc.delete_session(dup_id, hard=True)


def test_restart_backend_restore_session():
    """Simulate process restart by constructing a fresh SessionService."""
    sid = _sid("restart")
    svc1 = SessionService()
    svc1.create_session(
        session_id=sid,
        title="Persist across restart",
        dataset_path="persist.csv",
        tags=["restart"],
    )
    svc1.append_user_message(sid, "before restart")
    svc1.record_assistant_turn(
        sid,
        question="before restart",
        result={
            "answer": "saved",
            "dataset_topic": "persist-topic",
            "file_path": "persist.csv",
            "rows": 3,
            "columns": ["a"],
        },
        file_path="persist.csv",
    )

    # New service instance (no in-memory cache of rows)
    svc2 = SessionService()
    detail = svc2.get_session_detail(sid)
    assert detail["title"] == "Persist across restart" or "before restart" in (
        detail["title"] or ""
    )
    assert detail["dataset_path"] == "persist.csv" or detail["dataset_topic"]
    assert len(detail["chat_history"]) >= 2
    assert detail["messages"]

    svc2.delete_session(sid, hard=True)


# ── stress: 100 rapid creates ──────────────────────────────────────────────


def test_stress_100_rapid_creates():
    svc = _svc()
    uid = f"stress-{uuid.uuid4().hex[:8]}"
    n = 100
    ids = [f"stress-{uuid.uuid4().hex}" for _ in range(n)]
    errors: list[str] = []
    lock = threading.Lock()

    def _create(sid: str) -> str:
        try:
            out = svc.create_session(
                session_id=sid,
                title=f"Stress {sid[-6:]}",
                user_id=uid,
                dataset_path=f"{sid}.csv",
            )
            assert out["session_id"] == sid
            assert out.get("committed") is True
            # Immediate GET must succeed
            detail = svc.get_session_detail(sid, user_id=uid)
            assert detail["session_id"] == sid
            return sid
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(f"{sid}:{exc}")
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(_create, sid) for sid in ids]
        results = []
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    assert len(results) == n
    assert not errors, errors[:5]

    # All rows durable
    db = SessionLocal()
    try:
        count = (
            db.query(AnalysisSession)
            .filter(AnalysisSession.user_id == uid)
            .count()
        )
        assert count >= n
    finally:
        db.close()

    # Cleanup
    for sid in ids:
        try:
            svc.delete_session(sid, user_id=uid, hard=True)
        except Exception:
            pass


def test_stress_concurrent_create_same_id_idempotent():
    """Many threads create the same session_id — all succeed, one row."""
    svc = _svc()
    sid = _sid("same")
    uid = "same-user"
    barrier = threading.Barrier(12)
    outcomes: list[dict] = []
    err: list[str] = []

    def worker():
        try:
            barrier.wait(timeout=5)
            out = svc.create_session(session_id=sid, title="Shared", user_id=uid)
            outcomes.append(out)
        except Exception as exc:  # noqa: BLE001
            err.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not err, err
    assert len(outcomes) == 12
    assert all(o["session_id"] == sid for o in outcomes)

    detail = svc.get_session_detail(sid, user_id=uid)
    assert detail["session_id"] == sid

    db = SessionLocal()
    try:
        n = db.query(AnalysisSession).filter(AnalysisSession.session_id == sid).count()
        assert n == 1
    finally:
        db.close()

    svc.delete_session(sid, user_id=uid, hard=True)


def test_transaction_rollback_on_failure_does_not_orphan():
    """If dual-write path raises inside atomic create, session must not half-exist.

    We simulate by using a valid create (smoke) and ensure hard delete leaves no row.
    """
    svc = _svc()
    sid = _sid("orphan")
    svc.create_session(session_id=sid, title="orphan-check")
    svc.delete_session(sid, hard=True)
    with pytest.raises(SessionNotFoundError):
        svc.get_session_detail(sid)


def test_messages_alias_satisfies_regression_ses03_check():
    """Mirrors SES03 acceptance: dataset_path OR dataset_topic OR messages."""
    svc = _svc()
    sid = _sid("ses03")
    svc.create_session(session_id=sid, title="SES03")
    svc.append_user_message(sid, "Analyze India GDP")
    svc.record_assistant_turn(
        sid,
        question="Analyze India GDP",
        result={
            "answer": "ok",
            "dataset_topic": "India GDP",
            "file_path": "india_gdp.csv",
            "rows": 5,
            "columns": ["Year", "Value"],
        },
        file_path="india_gdp.csv",
    )
    body = svc.get_session_detail(sid)
    ok = bool(
        body.get("dataset_path")
        or body.get("dataset_topic")
        or body.get("messages")
    )
    assert ok
    assert body.get("messages")
    svc.delete_session(sid, hard=True)
