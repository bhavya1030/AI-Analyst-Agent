"""Phase 6: LangGraph / turn checkpoint persistence tests."""

from __future__ import annotations

import uuid

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.graph.checkpoint_service import CheckpointService, get_checkpoint_service
from backend.graph.state_codec import (
    decode_state,
    encode_state,
    extract_planner_state,
    merge_checkpoint_into_state,
)
from backend.sessions.router import router
from backend.sessions.service import SessionService


def _sid(prefix: str = "p6") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_encode_strips_dataframes():
    df = pd.DataFrame({"Year": [2000, 2001], "Value": [1.0, 2.0]})
    state = {
        "question": "forecast",
        "data": df,
        "last_dataset": df,
        "plan": ["forecast_data", "generate_insight"],
        "last_intent": "forecast",
        "dataset_url": "https://example.com/gdp.csv",
        "dataset_topic": "GDP",
        "file_path": None,
        "answer": "ok",
    }
    encoded = encode_state(state)
    assert "data" not in encoded or encoded.get("data") is None
    assert encoded.get("dataset_ref")
    assert encoded["dataset_ref"].get("dataset_url") == "https://example.com/gdp.csv"
    assert encoded.get("plan") == ["forecast_data", "generate_insight"]
    planner = extract_planner_state(state)
    assert planner.get("plan")
    assert planner.get("last_intent") == "forecast"


def test_save_and_resume_turn_checkpoint():
    svc = CheckpointService()
    sid = _sid("turn")
    state = {
        "question": "analyze gdp",
        "plan": [],
        "last_intent": "analysis",
        "last_operation": "eda",
        "dataset_topic": "GDP",
        "dataset_url": "https://example.com/gdp.csv",
        "answer": "Growth is steady",
        "last_columns_used": ["Year", "Value"],
        "dataset_profile": {"rows": 10, "time_columns": ["Year"]},
        "data": pd.DataFrame({"Year": [1, 2], "Value": [3.0, 4.0]}),
    }
    row = svc.save_turn_checkpoint(sid, state, source="turn")
    assert row["checkpoint_id"]
    assert row["is_latest"] is True
    assert row["graph_state"] is not None
    # No raw frame in stored JSON
    assert "data" not in (row["graph_state"] or {}) or row["graph_state"].get("data") is None

    loaded = svc.load_latest(sid, reload_frames=False)
    assert loaded is not None
    assert loaded["resumable"] is True
    assert loaded["planner_state"].get("last_intent") == "analysis"
    assert loaded["graph_state"].get("dataset_topic") == "GDP"

    resumed = svc.resume_session(sid, question="forecast it")
    assert resumed["resumable"] is True
    assert resumed["graph_state"]["question"] == "forecast it"
    assert resumed["planner_state"].get("last_intent") == "analysis"

    # Second checkpoint chains parent
    state2 = dict(state)
    state2["answer"] = "Forecast ready"
    state2["last_intent"] = "forecast"
    row2 = svc.save_turn_checkpoint(sid, state2, source="turn")
    assert row2["parent_checkpoint_id"] == row["checkpoint_id"]

    listing = svc.list_session_checkpoints(sid)
    assert listing["total"] >= 2

    svc.delete_session_checkpoints(sid)
    assert svc.has_checkpoint(sid) is False


def test_switch_session_loads_target():
    svc = get_checkpoint_service()
    a = _sid("sw-a")
    b = _sid("sw-b")
    svc.save_turn_checkpoint(
        a,
        {"question": "a", "dataset_topic": "Gold", "plan": [], "last_intent": "analysis"},
    )
    svc.save_turn_checkpoint(
        b,
        {"question": "b", "dataset_topic": "Oil", "plan": [], "last_intent": "forecast"},
    )
    switched = svc.switch_session(a, b)
    assert switched["switched"] is True
    assert switched["to_session_id"] == b
    assert switched["resumable"] is True
    assert switched["graph_state"].get("dataset_topic") == "Oil"

    svc.delete_session_checkpoints(a)
    svc.delete_session_checkpoints(b)


def test_merge_checkpoint_preserves_request_question():
    base = {"question": "new question", "topic_mismatch": False, "plan": []}
    cp = decode_state(
        encode_state(
            {
                "question": "old",
                "last_intent": "forecast",
                "dataset_topic": "GDP",
                "plan": ["forecast_data"],
            }
        ),
        reload_frames=False,
    )
    merged = merge_checkpoint_into_state(base, cp, prefer_checkpoint=True)
    assert merged["question"] == "new question"
    assert merged["last_intent"] == "forecast"
    assert merged["dataset_topic"] == "GDP"


def test_checkpoint_rest_apis():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    sessions = SessionService()
    ckpt = CheckpointService()

    sid = _sid("api")
    sessions.create_session(session_id=sid, title="Checkpoint API")
    ckpt.save_turn_checkpoint(
        sid,
        {
            "question": "analyze",
            "plan": ["run_eda"],
            "last_intent": "analysis",
            "dataset_topic": "GDP",
            "dataset_url": "https://example.com/x.csv",
            "answer": "done",
        },
    )

    r = client.get(f"/sessions/{sid}/checkpoints")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert body["items"][0]["checkpoint_id"]

    r2 = client.post(f"/sessions/{sid}/resume", json={})
    assert r2.status_code == 200
    resume = r2.json()
    assert resume["resumable"] is True
    assert resume["planner_state"].get("last_intent") == "analysis"
    assert resume["dataset_ref"] or resume.get("graph_state_preview")

    other = _sid("api2")
    sessions.create_session(session_id=other, title="Other")
    ckpt.save_turn_checkpoint(
        other, {"question": "x", "dataset_topic": "Oil", "plan": [], "last_intent": "x"}
    )
    r3 = client.post(
        "/sessions/switch",
        json={"from_session_id": sid, "to_session_id": other},
    )
    assert r3.status_code == 200
    assert r3.json()["switched"] is True
    assert r3.json()["to_session_id"] == other

    sessions.delete_session(sid, hard=True)
    sessions.delete_session(other, hard=True)
    ckpt.delete_session_checkpoints(sid)
    ckpt.delete_session_checkpoints(other)
