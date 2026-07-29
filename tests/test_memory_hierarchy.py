"""Phase 5: hierarchical memory load / inject / persist tests."""

from __future__ import annotations

import uuid

import pandas as pd

from backend.memory.hierarchy import MemoryHierarchyService, get_memory_hierarchy
from backend.memory.hierarchy_store import load_dataset_memory, make_dataset_key
from backend.sessions.service import SessionService


def _sid(prefix: str = "p5") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_load_inject_persist_roundtrip():
    svc = SessionService()
    mem = MemoryHierarchyService(l1_window=6)
    sid = _sid("rt")
    uid = f"u-{uuid.uuid4().hex[:6]}"

    svc.create_session(session_id=sid, title="GDP memory test", user_id=uid)
    svc.append_user_message(sid, "Analyze India GDP")
    svc.record_assistant_turn(
        sid,
        question="Analyze India GDP",
        result={
            "answer": "GDP shows steady growth.",
            "dataset_topic": "India GDP",
            "dataset_url": "https://example.com/gdp.csv",
            "last_intent": "analysis",
            "last_operation": "eda",
            "last_chart_type": "line",
            "last_columns_used": ["Year", "Value"],
            "dataset_profile": {
                "rows": 20,
                "numeric_columns": ["Value"],
                "time_columns": ["Year"],
            },
            "hypotheses": ["Growth continues"],
            "rows": 20,
            "columns": ["Year", "Value"],
        },
    )

    bundle = mem.load(
        sid,
        user_id=uid,
        question="Forecast it",
        dataset_topic="India GDP",
        dataset_url="https://example.com/gdp.csv",
    )
    assert bundle.session_id == sid
    assert len(bundle.l1_conversation.messages) >= 2
    assert bundle.l2_session.dataset_topic == "India GDP"
    assert bundle.l2_session.last_chart_type == "line"

    state = {
        "question": "Forecast it",
        "session_id": sid,
        "topic_mismatch": False,
    }
    state = mem.inject_into_state(state, bundle)
    assert state["memory_hierarchy_loaded"] is True
    assert state.get("last_chart_type") == "line"
    assert state.get("dataset_topic") == "India GDP"
    assert "memory" in state and state["memory"]["l1_conversation"]
    assert isinstance(state.get("recent_messages"), list)

    # Persist a forecast turn → L3 accumulates
    result = {
        "answer": "Forecast projects continued growth.",
        "dataset_topic": "India GDP",
        "dataset_url": "https://example.com/gdp.csv",
        "last_intent": "forecast",
        "last_operation": "forecast",
        "last_chart_type": "forecast",
        "last_forecast_target": "Value",
        "last_columns_used": ["Year", "Value"],
        "dataset_profile": {"rows": 20, "time_columns": ["Year"], "numeric_columns": ["Value"]},
        "data": pd.DataFrame({"Year": [2000, 2001], "Value": [1.0, 2.0]}),
        "rows": 2,
        "columns": ["Year", "Value"],
    }
    updated = mem.persist(sid, result, user_id=uid, question="Forecast it", prior=bundle)
    assert updated.l2_session.last_forecast_target == "Value"
    assert updated.l3_dataset.dataset_key
    assert updated.l3_dataset.analysis_count >= 1
    assert "Value" in updated.l3_dataset.last_forecast_targets or "Value" in (
        updated.l3_dataset.columns_frequently_used or []
    )

    # Second session on same dataset reuses L3
    sid2 = _sid("rt2")
    svc.create_session(session_id=sid2, title="GDP again", user_id=uid)
    bundle2 = mem.load(
        sid2,
        user_id=uid,
        dataset_topic="India GDP",
        dataset_url="https://example.com/gdp.csv",
    )
    assert bundle2.l3_dataset.analysis_count >= 1
    assert bundle2.l3_dataset.dataset_key == updated.l3_dataset.dataset_key

    from backend.memory.hierarchy_store import resolve_dataset_memory

    stored = resolve_dataset_memory(
        uid,
        dataset_url="https://example.com/gdp.csv",
        dataset_topic="India GDP",
    )
    assert stored is not None
    assert stored.analysis_count >= 1

    svc.delete_session(sid, hard=True)
    svc.delete_session(sid2, hard=True)


def test_inject_does_not_override_topic_mismatch():
    mem = get_memory_hierarchy()
    bundle = mem.load(_sid("mm"), question="gold prices")
    # Simulate L2 having old topic
    bundle.l2_session.dataset_topic = "India GDP"
    bundle.l2_session.last_intent = "analysis"

    state = {
        "question": "analyze gold",
        "topic_mismatch": True,
        "dataset_topic": None,
        "last_intent": None,
    }
    state = mem.inject_into_state(state, bundle)
    # Continuity fields skipped on topic mismatch
    assert state.get("dataset_topic") in (None, "")
    assert state.get("last_intent") in (None, "")
    # But structured memory still present
    assert state["session_memory"]["dataset_topic"] == "India GDP"


def test_l4_knowledge_loads_without_error():
    mem = MemoryHierarchyService()
    bundle = mem.load(_sid("k"), question="population statistics")
    assert bundle.l4_knowledge is not None
    assert isinstance(bundle.l4_knowledge.learned_datasets, list)
    assert isinstance(bundle.l4_knowledge.registry_datasets, list)


def test_memory_singleton():
    a = get_memory_hierarchy()
    b = get_memory_hierarchy()
    assert a is b
