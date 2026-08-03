"""Phase 1 Regression Tests — Session Becomes Single Source of Truth for Dataset Ownership.

Verifies:
1. Session DB permanently owns dataset_id, dataset_name, dataset_path, fingerprint, schema, summary, active_dataset.
2. All follow-up questions reuse the active session dataset without retrieval or auto-clearing.
3. Uploading another dataset triggers a dataset switch.
"""

from __future__ import annotations

import uuid
from pathlib import Path
import pandas as pd

from backend.orchestrator.state_builder import build_analyst_state, get_session_snapshot, SessionSnapshot
from backend.memory.continuity import should_reuse_session_dataset, is_new_dataset_topic
from backend.sessions.service import SessionService
from backend.agents.planner_agent import planner_agent


def _sid(prefix: str = "p1") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_session_ownership_persistence(tmp_path: Path):
    """Test that AnalysisSession DB permanently stores and owns all Phase 1 dataset fields."""
    svc = SessionService()
    sid = _sid()
    uid = f"u-{uuid.uuid4().hex[:6]}"
    
    csv_file = tmp_path / "titanic.csv"
    csv_file.write_text(
        "PassengerId,Survived,Pclass,Name,Sex,Age,Fare\n"
        "1,0,3,Braund,male,22,7.25\n"
        "2,1,1,Cumings,female,38,71.28\n",
        encoding="utf-8"
    )

    svc.create_session(
        session_id=sid,
        title="Titanic Analysis",
        dataset_id="ds-titanic-123",
        dataset_name="titanic.csv",
        dataset_path=str(csv_file),
        user_id=uid,
    )

    # Record turn
    turn_result = {
        "dataset_path": str(csv_file),
        "dataset_name": "titanic.csv",
        "dataset_id": "ds-titanic-123",
        "dataset_topic": "titanic",
        "columns": ["PassengerId", "Survived", "Pclass", "Name", "Sex", "Age", "Fare"],
        "rows": 2,
        "dataset_profile": {"rows": 2, "numeric_columns": ["Age", "Fare"]},
        "answer": "Loaded Titanic dataset.",
    }
    svc.record_assistant_turn(sid, question="Analyze Titanic", result=turn_result, user_id=uid)

    snapshot = get_session_snapshot(sid, user_id=uid)
    assert snapshot is not None
    assert snapshot.active_dataset is True
    assert snapshot.dataset_path == str(csv_file)
    assert snapshot.dataset_name == "titanic.csv"
    assert snapshot.dataset_id == "ds-titanic-123"
    assert snapshot.fingerprint == "ds-titanic-123"
    assert "PassengerId" in (snapshot.schema or [])


def test_followups_never_clear_session_dataset(tmp_path: Path):
    """Test that follow-up analytical questions never clear active session dataset."""
    csv_file = tmp_path / "titanic.csv"
    csv_file.write_text(
        "PassengerId,Survived,Pclass,Name,Sex,Age,Fare\n"
        "1,0,3,Braund,male,22,7.25\n",
        encoding="utf-8"
    )

    snapshot = SessionSnapshot(
        dataset_topic="titanic",
        dataset_name="titanic.csv",
        dataset_path=str(csv_file),
        dataset_id="ds-titanic-123",
        active_dataset=True,
        fingerprint="ds-titanic-123",
        schema=["PassengerId", "Survived", "Pclass", "Name", "Sex", "Age", "Fare"],
        summary={"rows": 1},
    )

    followups = [
        "show first 5 rows",
        "show missing values",
        "describe dataset",
        "plot histogram",
        "average fare",
        "correlation matrix",
        "show duplicates",
        "forecast passengers",
    ]

    for q in followups:
        reuse, mismatch = should_reuse_session_dataset(
            question=q,
            dataset_topic=snapshot.dataset_topic,
            dataset_path=snapshot.dataset_path,
            dataset_url=snapshot.dataset_url,
            has_frame=True,
        )
        assert reuse is True, f"Failed reuse for '{q}'"
        assert mismatch is False, f"Failed mismatch for '{q}'"

        state = build_analyst_state(snapshot, question=q, file_path=None)
        assert state["active_dataset"] is True, f"active_dataset dropped for '{q}'"
        assert state["topic_mismatch"] is False, f"topic_mismatch True for '{q}'"
        assert state["reuse_active_dataset"] is True, f"reuse_active_dataset False for '{q}'"
        assert state["dataset_path"] == str(csv_file), f"dataset_path dropped for '{q}'"

        # Verify planner routes directly without retrieval
        state = planner_agent(state)
        plan = state.get("plan") or []
        assert "retrieve_dataset" not in plan, f"Retrieval erroneously planned for '{q}'"
        assert "dataset_search_agent" not in plan, f"Search erroneously planned for '{q}'"


def test_new_upload_triggers_dataset_switch(tmp_path: Path):
    """Test that providing a different file_path triggers dataset switch."""
    p1 = tmp_path / "titanic.csv"
    p1.write_text("a,b\n1,2\n", encoding="utf-8")

    p2 = tmp_path / "iris.csv"
    p2.write_text("x,y\n3,4\n", encoding="utf-8")

    snapshot = SessionSnapshot(
        dataset_topic="titanic",
        dataset_name="titanic.csv",
        dataset_path=str(p1),
        dataset_id="ds-1",
        active_dataset=True,
    )

    reuse, mismatch = should_reuse_session_dataset(
        question="Analyze Iris",
        dataset_topic=snapshot.dataset_topic,
        dataset_path=snapshot.dataset_path,
        dataset_url=snapshot.dataset_url,
        has_frame=True,
        file_path_override=str(p2),
    )
    assert reuse is False
    assert mismatch is True
