"""Phase 6 Regression Tests — Production Repository Cleanup.

Verifies:
1. Obsolete functions and dead heuristics have been safely removed / simplified.
2. All backend request orchestrator and state builder components run cleanly.
"""

from __future__ import annotations

from backend.memory.continuity import is_new_dataset_topic, should_reuse_session_dataset
from backend.utils.reference_resolver import resolve_question_references
from backend.utils.intent_classifier import classify_intents, SUPPORTED_INTENTS
from backend.agents.planner_agent import planner_agent


def test_clean_architecture_pipeline():
    """End-to-end trace of Phase 1-5 pipeline clean execution."""
    # 1. Classified intent
    intents = classify_intents("show missing values")
    assert intents == ["eda"]

    # 2. Reference resolution
    resolved = resolve_question_references(
        "show missing values",
        dataset_name="titanic.csv",
        has_active_dataset=True,
    )
    assert resolved == "Show missing values in dataset titanic.csv"

    # 3. Session dataset reuse
    reuse, mismatch = should_reuse_session_dataset(
        question=resolved,
        dataset_topic="titanic",
        dataset_path="/data/titanic.csv",
        dataset_url=None,
        has_frame=True,
    )
    assert reuse is True
    assert mismatch is False

    # 4. Pure Intent Planner
    state = {
        "question": resolved,
        "intents": intents,
        "dataset_name": "titanic.csv",
        "dataset_path": "/data/titanic.csv",
        "has_active_dataset": True,
        "topic_mismatch": False,
        "data": True,
    }
    result = planner_agent(state)
    assert result["reuse_active_dataset"] is True
    assert "retrieve_dataset" not in result["plan"]
    assert "run_eda" in result["plan"]
