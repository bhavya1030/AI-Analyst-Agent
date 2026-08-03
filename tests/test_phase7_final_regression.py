"""Phase 7 Final Comprehensive Regression Suite.

Covers all 4 core architectural guarantees:
1. Titanic Scenario: Multi-turn analytical follow-ups NEVER lose active dataset.
2. Topic Switch Scenario: Explicit new dataset request DOES trigger topic switch.
3. New Chat Scenario: New Chat completely resets active dataset.
4. Pronoun Resolution Scenario: Ambiguous pronouns and chart references are resolved explicitly.
"""

from __future__ import annotations

import uuid
from pathlib import Path
import pandas as pd

from backend.agents.conversation_context_agent import conversation_context_agent
from backend.agents.planner_agent import planner_agent
from backend.memory.continuity import should_reuse_session_dataset
from backend.orchestrator.state_builder import build_analyst_state, get_session_snapshot
from backend.sessions.service import SessionService
from backend.utils.intent_classifier import classify_intents
from backend.utils.reference_resolver import resolve_question_references


def _sid(prefix: str = "p7") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_scenario_1_titanic_analytical_followups(tmp_path: Path):
    """
    Scenario 1: Upload titanic.csv -> multi-turn follow-ups NEVER lose active dataset or trigger retrieval.
    """
    svc = SessionService()
    sid = _sid("titanic")
    uid = f"u-{uuid.uuid4().hex[:6]}"

    csv_file = tmp_path / "titanic.csv"
    csv_file.write_text(
        "PassengerId,Survived,Pclass,Name,Sex,Age,Fare\n"
        "1,0,3,Braund,male,22,7.25\n"
        "2,1,1,Cumings,female,38,71.28\n",
        encoding="utf-8",
    )

    # 1. Upload & Create Session
    svc.create_session(
        session_id=sid,
        title="Titanic Analysis",
        dataset_id="ds-titanic-100",
        dataset_name="titanic.csv",
        dataset_path=str(csv_file),
        user_id=uid,
    )

    turn_result = {
        "dataset_path": str(csv_file),
        "dataset_name": "titanic.csv",
        "dataset_id": "ds-titanic-100",
        "dataset_topic": "titanic",
        "columns": ["PassengerId", "Survived", "Pclass", "Name", "Sex", "Age", "Fare"],
        "rows": 2,
        "answer": "Loaded Titanic dataset.",
    }
    svc.record_assistant_turn(sid, question="Analyze it", result=turn_result, user_id=uid)

    followup_questions = [
        "Show missing values",
        "Describe dataset",
        "Plot histogram of age",
        "Average fare",
        "Show duplicates",
        "Correlation matrix",
    ]

    for q in followup_questions:
        snapshot = get_session_snapshot(sid, user_id=uid)
        assert snapshot is not None, f"Failed to retrieve snapshot for {q}"
        assert snapshot.active_dataset is True, f"Active dataset lost for {q}"
        assert snapshot.dataset_path == str(csv_file), f"Dataset path corrupted for {q}"

        state = build_analyst_state(snapshot, question=q, file_path=None)
        assert state["has_active_dataset"] is True, f"has_active_dataset false for {q}"
        assert state["active_dataset"] is True, f"active_dataset false for {q}"
        assert state["topic_mismatch"] is False, f"topic_mismatch triggered for {q}"

        # Context Agent
        state = conversation_context_agent(state)
        assert state["reuse_active_dataset"] is True, f"reuse_active_dataset false for {q}"

        # Planner
        planned = planner_agent(state)
        plan = planned["plan"]

        # CRITICAL GUARANTEE: NEVER trigger dataset discovery / retrieval
        assert "retrieve_dataset" not in plan, f"Query '{q}' erroneously triggered retrieve_dataset in plan: {plan}"
        assert "prepare_dataset" not in plan, f"Query '{q}' erroneously triggered prepare_dataset in plan: {plan}"
        assert "dataset_topic_agent" not in plan, f"Query '{q}' erroneously triggered dataset_topic_agent in plan: {plan}"
        assert "dataset_search_agent" not in plan, f"Query '{q}' erroneously triggered dataset_search_agent in plan: {plan}"
        assert planned.get("reuse_active_dataset") is True


def test_scenario_2_explicit_topic_switch(tmp_path: Path):
    """
    Scenario 2: Active dataset titanic.csv -> "Analyze gold prices" MUST trigger topic switch.
    """
    csv_file = tmp_path / "titanic.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")

    reuse, mismatch = should_reuse_session_dataset(
        question="Analyze gold prices",
        dataset_topic="titanic",
        dataset_path=str(csv_file),
        dataset_url=None,
        has_frame=True,
    )

    assert reuse is False, "Expected reuse=False for explicit topic switch 'Analyze gold prices'"
    assert mismatch is True, "Expected mismatch=True for explicit topic switch 'Analyze gold prices'"


def test_scenario_3_new_chat_clears_active_dataset(tmp_path: Path):
    """
    Scenario 3: Upload titanic.csv -> New Chat -> "Show missing values" has active_dataset=False.
    """
    svc = SessionService()
    sid_old = _sid("old-chat")
    sid_new = _sid("new-chat")
    uid = f"u-{uuid.uuid4().hex[:6]}"

    csv_file = tmp_path / "titanic.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")

    # Session 1: Old Chat
    svc.create_session(
        session_id=sid_old,
        title="Old Titanic Chat",
        dataset_id="ds-titanic-1",
        dataset_name="titanic.csv",
        dataset_path=str(csv_file),
        user_id=uid,
    )

    # Session 2: User clicks "New Chat" -> Fresh session without dataset
    svc.create_session(
        session_id=sid_new,
        title="New analysis",
        user_id=uid,
    )

    snapshot_new = get_session_snapshot(sid_new, user_id=uid)
    assert snapshot_new is not None
    assert snapshot_new.active_dataset is False

    state_new = build_analyst_state(snapshot_new, question="Show missing values", file_path=None)
    assert state_new["active_dataset"] is False

    planned_new = planner_agent(state_new)
    # Planner must NOT reuse old dataset
    assert planned_new.get("reuse_active_dataset") is not True
    assert "retrieve_dataset" in planned_new["plan"] or "load_data" in planned_new["plan"]


def test_scenario_4_pronoun_and_chart_reference_resolution():
    """
    Scenario 4: Ambiguous pronouns and chart references are resolved explicitly.
    """
    ds_name = "titanic.csv"

    # 1. Dataset Pronoun
    res_ds = resolve_question_references("Describe it", dataset_name=ds_name, has_active_dataset=True)
    assert res_ds == "Describe the dataset titanic.csv"

    # 2. Chart Reference
    res_chart = resolve_question_references(
        "Explain this chart",
        last_chart="histogram of Age",
        has_active_dataset=True,
    )
    assert res_chart == "Explain the histogram of Age chart"

    # 3. Operation Reference
    res_op = resolve_question_references(
        "What does this show?",
        last_operation="correlation matrix",
        has_active_dataset=True,
    )
    assert res_op == "Explain the correlation matrix chart"
