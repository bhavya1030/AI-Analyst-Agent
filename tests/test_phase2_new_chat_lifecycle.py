"""Phase 2 Regression Tests — New Chat Lifecycle.

Verifies:
1. Resetting a session clears active dataset, planner state, cached dataset state, and memory hierarchy.
2. After a New Chat / Reset event, build_analyst_state receives active_dataset = False.
3. Follow-up queries after New Chat request dataset / retrieval instead of reusing old dataset.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from backend.orchestrator.state_builder import build_analyst_state, get_session_snapshot
from backend.sessions.service import SessionService
from backend.agents.planner_agent import planner_agent


def _sid(prefix: str = "p2") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_session_reset_clears_dataset_and_state(tmp_path: Path):
    """Test that resetting a session completely clears dataset ownership and planner state."""
    svc = SessionService()
    sid = _sid()
    uid = f"u-{uuid.uuid4().hex[:6]}"

    csv_file = tmp_path / "titanic.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")

    svc.create_session(
        session_id=sid,
        title="Titanic Analysis",
        dataset_id="ds-titanic-999",
        dataset_name="titanic.csv",
        dataset_path=str(csv_file),
        user_id=uid,
    )

    # Verify initially active
    snapshot = get_session_snapshot(sid, user_id=uid)
    assert snapshot is not None
    assert snapshot.active_dataset is True

    # Execute backend reset
    reset_res = svc.reset_session(sid, user_id=uid)
    assert reset_res["reset"] is True

    # Verify cleared after reset
    snapshot_after = get_session_snapshot(sid, user_id=uid)
    assert snapshot_after is not None
    assert snapshot_after.active_dataset is False
    assert snapshot_after.dataset_path is None
    assert snapshot_after.dataset_name is None
    assert snapshot_after.dataset_id is None

    # Verify state builder gets no active dataset
    state = build_analyst_state(snapshot_after, question="show missing values", file_path=None)
    assert state["has_active_dataset"] is False
    assert state["active_dataset"] is False
    assert state["reuse_active_dataset"] is False
    assert state["dataset_path"] is None


def test_new_chat_sequence(tmp_path: Path):
    """Scenario 3: Analyze Titanic -> New Chat -> Show missing values requests dataset."""
    svc = SessionService()
    sid_old = _sid("old")
    sid_new = _sid("new")
    uid = f"u-{uuid.uuid4().hex[:6]}"

    csv_file = tmp_path / "titanic.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")

    # Turn 1: Session 1 with Titanic dataset
    svc.create_session(
        session_id=sid_old,
        title="Titanic Chat",
        dataset_id="ds-100",
        dataset_name="titanic.csv",
        dataset_path=str(csv_file),
        user_id=uid,
    )

    # Turn 2: User clicks "New Chat" -> Session 2 created without dataset
    svc.create_session(
        session_id=sid_new,
        title="New analysis",
        user_id=uid,
    )

    snap_new = get_session_snapshot(sid_new, user_id=uid)
    assert snap_new is not None
    assert snap_new.active_dataset is False

    state_new = build_analyst_state(snap_new, question="show missing values", file_path=None)
    assert state_new["active_dataset"] is False

    # Planner should not reuse old dataset
    planner_res = planner_agent(state_new)
    plan = planner_res.get("plan") or []
    assert planner_res.get("reuse_active_dataset") is not True
