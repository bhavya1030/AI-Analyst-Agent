"""Phase 8: user model, auth resolution, session ownership isolation."""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth.context import ANONYMOUS_USER_ID, AuthUser
from backend.auth.deps import resolve_auth_user
from backend.auth.service import UserService, get_user_service, normalize_user_id
from backend.sessions.router import router
from backend.sessions.service import (
    SessionAccessDenied,
    SessionService,
)


def _uid(prefix: str = "u") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _sid(prefix: str = "s") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def test_normalize_and_seed_anonymous():
    svc = get_user_service()
    user = svc.get_or_create(ANONYMOUS_USER_ID)
    assert user.id == ANONYMOUS_USER_ID
    assert user.is_anonymous is True
    assert normalize_user_id("") == ANONYMOUS_USER_ID
    assert normalize_user_id("alice@example.com")  # safe-ish id


def test_resolve_auth_header_and_anonymous():
    anon = resolve_auth_user()
    assert anon.user_id == ANONYMOUS_USER_ID
    assert anon.auth_method == "anonymous"

    auth = resolve_auth_user(x_user_id="alice-1")
    assert auth.user_id == "alice-1"
    assert auth.auth_method == "header"
    assert auth.is_anonymous is False

    # User row created
    row = UserService().get("alice-1")
    assert row is not None


def test_session_ownership_isolation():
    svc = SessionService()
    alice = _uid("alice")
    bob = _uid("bob")
    sid = _sid("own")

    created = svc.create_session(session_id=sid, title="Alice only", user_id=alice)
    assert created["user_id"] == alice

    # Alice can load
    detail = svc.get_session_detail(sid, user_id=alice)
    assert detail["session_id"] == sid

    # Bob cannot load or mutate
    try:
        svc.get_session_detail(sid, user_id=bob)
        assert False, "expected SessionAccessDenied"
    except SessionAccessDenied:
        pass

    try:
        svc.rename_session(sid, "hacked", user_id=bob)
        assert False, "expected SessionAccessDenied"
    except SessionAccessDenied:
        pass

    try:
        svc.ensure_session(sid, user_id=bob)
        assert False, "expected SessionAccessDenied"
    except SessionAccessDenied:
        pass

    # Lists are isolated
    alice_list = svc.list_session_ids(user_id=alice)
    bob_list = svc.list_session_ids(user_id=bob)
    assert sid in alice_list
    assert sid not in bob_list

    svc.delete_session(sid, user_id=alice, hard=True)


def test_api_isolation_with_headers():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    alice = _uid("api-a")
    bob = _uid("api-b")
    sid = _sid("api-s")

    r = client.post(
        "/sessions",
        json={"session_id": sid, "title": "Private"},
        headers={"X-User-Id": alice},
    )
    assert r.status_code == 201
    assert r.json()["user_id"] == alice

    # Bob list does not include Alice session
    r2 = client.get("/sessions?detail=true", headers={"X-User-Id": bob})
    assert r2.status_code == 200
    ids = [i["session_id"] for i in r2.json()["items"]]
    assert sid not in ids

    # Bob GET → 403
    r3 = client.get(f"/sessions/{sid}", headers={"X-User-Id": bob})
    assert r3.status_code == 403
    assert r3.json()["code"] == "SESSION_ACCESS_DENIED"

    # Alice GET → 200
    r4 = client.get(f"/sessions/{sid}", headers={"X-User-Id": alice})
    assert r4.status_code == 200
    assert r4.json()["user_id"] == alice

    # /auth/me
    r5 = client.get("/auth/me", headers={"X-User-Id": alice})
    assert r5.status_code == 200
    assert r5.json()["user_id"] == alice
    assert r5.json()["auth_method"] == "header"

    # Anonymous default
    r6 = client.get("/auth/me")
    assert r6.status_code == 200
    assert r6.json()["user_id"] == ANONYMOUS_USER_ID

    client.delete(f"/sessions/{sid}?hard=true", headers={"X-User-Id": alice})


def test_auth_user_dataclass():
    u = AuthUser(user_id="x", is_anonymous=False, auth_method="header")
    d = u.to_dict()
    assert d["user_id"] == "x"
    assert d["auth_method"] == "header"
