"""Conversation Memory v2 — continuity, restore, planner injection."""

from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd

from backend.agents.conversation_context_agent import conversation_context_agent
from backend.agents.planner_agent import planner_agent
from backend.orchestrator.state_builder import build_analyst_state as _build_state
from backend.orchestrator.state_builder import _question_is_new_topic
from backend.memory.continuity import (
    build_planner_injection,
    is_follow_up_question,
    is_new_dataset_topic,
    should_reuse_session_dataset,
)
from backend.memory.hierarchy import MemoryHierarchyService
from backend.memory.restore import apply_restored_frame, restore_dataframe
from backend.sessions.service import SessionService


def _sid(prefix: str = "mc") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_follow_up_detection():
    assert is_follow_up_question("show histogram")
    assert is_follow_up_question("correlation")
    assert is_follow_up_question("forecast")
    assert is_follow_up_question("forecast it")
    assert is_follow_up_question("compare with China")
    assert not is_follow_up_question("analyze gold prices over 20 years")


def test_show_histogram_not_new_topic():
    assert not is_new_dataset_topic(
        "show histogram", "India GDP", has_active_dataset=True
    )
    assert not is_new_dataset_topic(
        "correlation", "India GDP", has_active_dataset=True
    )
    assert not is_new_dataset_topic(
        "forecast", "India GDP", has_active_dataset=True
    )
    assert not is_new_dataset_topic(
        "compare with China", "India GDP", has_active_dataset=True
    )
    # True topic change
    assert is_new_dataset_topic(
        "analyze gold prices", "India GDP", has_active_dataset=True
    )
    # Legacy helper used by main
    assert not _question_is_new_topic(
        "show histogram", "India GDP", has_active_dataset=True
    )


def test_should_reuse_session_dataset():
    reuse, mismatch = should_reuse_session_dataset(
        question="show histogram",
        dataset_topic="India GDP",
        dataset_path="/tmp/india_gdp.csv",
        dataset_url=None,
        has_frame=False,
    )
    assert reuse is True
    assert mismatch is False

    reuse2, mismatch2 = should_reuse_session_dataset(
        question="analyze bitcoin prices",
        dataset_topic="India GDP",
        dataset_path="/tmp/india_gdp.csv",
        dataset_url=None,
        has_frame=True,
    )
    assert reuse2 is False
    assert mismatch2 is True


def test_restore_dataframe(tmp_path: Path):
    p = tmp_path / "gdp.csv"
    p.write_text("Year,GDP\n2000,1\n2001,2\n2002,3\n", encoding="utf-8")
    df = restore_dataframe(dataset_path=str(p))
    assert df is not None
    assert len(df) == 3
    state = apply_restored_frame({}, df)
    assert state["data"] is not None
    assert state["reuse_active_dataset"] is True
    assert state["needs_user_data"] is False


def test_build_state_keeps_dataset_on_histogram(tmp_path: Path):
    p = tmp_path / "india_gdp.csv"
    p.write_text("Year,GDP\n2010,1.0\n2011,1.1\n2012,1.2\n", encoding="utf-8")

    class FakeSession:
        dataset_path = str(p)
        dataset_url = None
        dataset_topic = "India GDP"
        dataset_id = "ds-1"
        last_column = "GDP"
        last_columns = ["Year", "GDP"]
        last_chart_type = "line"
        last_intent = "analysis"
        last_operation = "eda"
        last_forecast_target = None

    state = _build_state(FakeSession(), question="show histogram", file_path=None)
    assert state.get("topic_mismatch") is False
    assert state.get("reuse_active_dataset") is True
    assert state.get("data") is not None
    assert state.get("needs_user_data") is False
    assert state.get("file_path") == str(p) or state.get("dataset_path") == str(p)


def test_planner_injection_skips_discovery_when_data_present():
    df = pd.DataFrame({"Year": [2000, 2001, 2002], "GDP": [1.0, 1.1, 1.2]})
    state = {
        "question": "show histogram",
        "data": df,
        "dataset_topic": "India GDP",
        "file_path": "/data/india_gdp.csv",
        "reuse_active_dataset": True,
        "planner_skip_upload": True,
        "topic_mismatch": False,
        "force_reload_dataset": False,
        "columns": ["Year", "GDP"],
        "rows": 3,
    }
    state.update(build_planner_injection(state))
    out = planner_agent(state)
    plan = out.get("plan") or []
    discovery = {
        "dataset_search_agent",
        "retrieve_dataset",
        "prepare_dataset",
        "fetch_data",
        "load_data",
        "dataset_topic_agent",
    }
    assert not (set(plan) & discovery), f"plan unexpectedly rediscovers: {plan}"
    assert out.get("needs_user_data") in (False, None)
    assert out.get("data") is not None


def test_conversation_context_resolves_histogram():
    df = pd.DataFrame({"Year": [1, 2], "GDP": [1.0, 2.0]})
    state = {
        "question": "show histogram",
        "data": df,
        "dataset_topic": "India GDP",
        "session_memory": {"dataset_topic": "India GDP", "last_columns": ["Year", "GDP"]},
        "topic_mismatch": False,
    }
    out = conversation_context_agent(state)
    assert out.get("reuse_active_dataset") is True
    q = (out.get("question") or "").lower()
    assert "histogram" in q
    assert "india" in q or "gdp" in q


def test_session_restore_and_memory_inject(tmp_path: Path):
    p = tmp_path / "pop.csv"
    p.write_text("Year,Population\n2000,100\n2001,110\n", encoding="utf-8")
    svc = SessionService()
    mem = MemoryHierarchyService(l1_window=6)
    sid = _sid("restore")
    uid = f"u-{uuid.uuid4().hex[:6]}"
    svc.create_session(session_id=sid, title="Pop", user_id=uid)
    svc.append_user_message(sid, "Analyze population", user_id=uid)
    svc.record_assistant_turn(
        sid,
        question="Analyze population",
        result={
            "answer": "Population grew.",
            "dataset_topic": "population",
            "dataset_name": "World Population",
            "file_path": str(p),
            "local_path": str(p),
            "last_intent": "analysis",
            "last_columns_used": ["Year", "Population"],
            "columns": ["Year", "Population"],
            "rows": 2,
            "dataset_profile": {
                "rows": 2,
                "numeric_columns": ["Population"],
                "time_columns": ["Year"],
            },
        },
        file_path=str(p),
        user_id=uid,
    )

    bundle = mem.load(sid, user_id=uid, question="show histogram")
    assert bundle.l2_session.dataset_path == str(p) or bundle.l2_session.dataset_topic

    state = {
        "question": "show histogram",
        "session_id": sid,
        "topic_mismatch": False,
        "data": None,
    }
    state = mem.inject_into_state(state, bundle)
    assert state.get("data") is not None or state.get("file_path")
    assert state.get("reuse_active_dataset") is True or state.get("planner_skip_upload") is True
    assert state.get("needs_user_data") is False
    assert state.get("session_dataframe_restored") is True or state.get("data") is not None


def test_conversation_continuity_end_to_end(tmp_path: Path):
    """Analyze → show histogram keeps the same frame without upload."""
    p = tmp_path / "india_gdp.csv"
    p.write_text(
        "Year,GDP\n"
        + "\n".join(f"{2000+i},{100+i}" for i in range(15))
        + "\n",
        encoding="utf-8",
    )
    svc = SessionService()
    mem = MemoryHierarchyService()
    sid = _sid("e2e")
    uid = f"u-{uuid.uuid4().hex[:6]}"
    svc.create_session(session_id=sid, title="GDP", user_id=uid)

    # Turn 1 — analyze
    df = pd.read_csv(p)
    r1 = {
        "answer": "GDP trend is up.",
        "dataset_topic": "India GDP",
        "dataset_name": "India GDP",
        "file_path": str(p),
        "local_path": str(p),
        "data": df,
        "columns": ["Year", "GDP"],
        "rows": len(df),
        "last_intent": "analysis",
        "last_operation": "eda",
        "last_chart_type": "line",
        "last_columns_used": ["Year", "GDP"],
        "dataset_profile": {
            "rows": len(df),
            "numeric_columns": ["GDP"],
            "time_columns": ["Year"],
            "column_names": ["Year", "GDP"],
        },
        "charts": [{"type": "line"}],
    }
    svc.append_user_message(sid, "Analyze India GDP", user_id=uid)
    svc.record_assistant_turn(
        sid, question="Analyze India GDP", result=r1, file_path=str(p), user_id=uid
    )
    bundle = mem.persist(sid, r1, user_id=uid, question="Analyze India GDP")

    # Turn 2 — follow-up via detail + build_state
    detail = svc.get_session_detail(sid, user_id=uid)

    class S:
        pass

    s = S()
    if isinstance(detail, dict):
        s.dataset_path = detail.get("dataset_path") or str(p)
        s.dataset_url = detail.get("dataset_url")
        s.dataset_topic = detail.get("dataset_topic") or "India GDP"
        s.dataset_id = detail.get("dataset_id")
        s.last_column = detail.get("last_column") or "GDP"
        s.last_columns = detail.get("last_columns") or ["Year", "GDP"]
        s.last_chart_type = detail.get("last_chart_type")
        s.last_intent = detail.get("last_intent")
        s.last_operation = detail.get("last_operation")
        s.last_forecast_target = detail.get("last_forecast_target")
    else:
        s.dataset_path = getattr(detail, "dataset_path", None) or str(p)
        s.dataset_url = getattr(detail, "dataset_url", None)
        s.dataset_topic = getattr(detail, "dataset_topic", None) or "India GDP"
        s.dataset_id = getattr(detail, "dataset_id", None)
        s.last_column = getattr(detail, "last_column", None) or "GDP"
        s.last_columns = getattr(detail, "last_columns", None) or ["Year", "GDP"]
        s.last_chart_type = getattr(detail, "last_chart_type", None)
        s.last_intent = getattr(detail, "last_intent", None)
        s.last_operation = getattr(detail, "last_operation", None)
        s.last_forecast_target = getattr(detail, "last_forecast_target", None)

    state = _build_state(s, question="show histogram", file_path=None)
    assert state["topic_mismatch"] is False, state
    assert state["data"] is not None
    state = mem.inject_into_state(state, bundle)
    state = conversation_context_agent(state)
    state = planner_agent(state)
    plan = state.get("plan") or []
    assert state.get("data") is not None
    assert state.get("needs_user_data") in (False, None)
    assert "load_data" not in plan
    assert "dataset_search_agent" not in plan
    assert "retrieve_dataset" not in plan


def test_titanic_analytical_followups_reuse_active_dataset(tmp_path: Path):
    """
    Regression test: Analytical follow-up questions on an active Titanic dataset MUST reuse
    the dataset without clearing state or calling retrieval.
    """
    p = tmp_path / "titanic.csv"
    p.write_text(
        "PassengerId,Survived,Pclass,Name,Sex,Age,Fare\n"
        "1,0,3,Braund,male,22,7.25\n"
        "2,1,1,Cumings,female,38,71.28\n"
        "3,1,3,Heikkinen,female,26,7.925\n",
        encoding="utf-8",
    )

    class Session:
        dataset_path = str(p)
        dataset_url = None
        dataset_topic = "titanic"
        dataset_name = "titanic.csv"
        dataset_id = "ds-titanic"
        last_column = "Fare"
        last_columns = ["Age", "Fare"]
        last_chart_type = "histogram"
        last_intent = "analysis"
        last_operation = "eda"
        last_forecast_target = None

    s = Session()
    df = pd.read_csv(p)

    followups = [
        "show missing values",
        "describe dataset",
        "summary statistics",
        "plot histogram",
        "correlation matrix",
        "average fare",
        "show duplicates",
    ]

    for q in followups:
        reuse, mismatch = should_reuse_session_dataset(
            question=q,
            dataset_topic=s.dataset_topic,
            dataset_path=s.dataset_path,
            dataset_url=s.dataset_url,
            has_frame=True,
        )
        assert reuse is True, f"Failed reuse=True for '{q}'"
        assert mismatch is False, f"Failed mismatch=False for '{q}'"

        state = _build_state(s, question=q, file_path=None)
        assert state["topic_mismatch"] is False, f"State topic_mismatch failed for '{q}'"
        assert state["reuse_active_dataset"] is True, f"State reuse_active_dataset failed for '{q}'"
        assert state["has_active_dataset"] is True, f"State has_active_dataset failed for '{q}'"
        assert state["dataset_path"] == str(p), f"Dataset path dropped for '{q}'"
        assert state["data"] is not None, f"DataFrame dropped for '{q}'"

        state = planner_agent(state)
        plan = state.get("plan") or []

        assert "retrieve_dataset" not in plan, f"Retrieval erroneously planned for '{q}'"
        assert "dataset_search_agent" not in plan, f"Search erroneously planned for '{q}'"
        assert "fetch_data" not in plan, f"Fetch erroneously planned for '{q}'"


def test_legitimate_topic_switches(tmp_path: Path):
    """
    Regression test: Explicit requests for a NEW dataset MUST trigger topic mismatch and retrieval.
    """
    p = tmp_path / "titanic.csv"

    class Session:
        dataset_path = str(p)
        dataset_url = None
        dataset_topic = "titanic"
        dataset_name = "titanic.csv"
        dataset_id = "ds-titanic"
        last_column = None
        last_columns = []
        last_chart_type = None
        last_intent = None
        last_operation = None
        last_forecast_target = None

    s = Session()

    switches = [
        "Analyze gold prices",
        "Analyze IPL dataset",
        "Load GDP dataset",
        "Switch to COVID dataset",
    ]

    for q in switches:
        reuse, mismatch = should_reuse_session_dataset(
            question=q,
            dataset_topic=s.dataset_topic,
            dataset_path=s.dataset_path,
            dataset_url=s.dataset_url,
            has_frame=True,
        )
        assert reuse is False, f"Expected reuse=False for topic switch '{q}'"
        assert mismatch is True, f"Expected mismatch=True for topic switch '{q}'"
