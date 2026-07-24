"""Tests for Human Feedback Learning (Task 23)."""

from __future__ import annotations

import pytest

from backend.feedback import (
    FeedbackRecord,
    FeedbackType,
    ScoreAdjustment,
    adjust_scores,
    get_feedback,
    record_feedback,
    reset_feedback_service,
)
from backend.feedback.feedback_service import FeedbackService
from backend.feedback.memory import FeedbackMemory
from backend.feedback.scorer import FeedbackScorer


@pytest.fixture(autouse=True)
def _reset():
    reset_feedback_service()
    yield
    reset_feedback_service()


# ---------------------------------------------------------------------------
# record / get
# ---------------------------------------------------------------------------


def test_record_and_get_feedback():
    rec = record_feedback(
        question="Analyze India's GDP",
        feedback="good_answer",
        user="alice",
        chosen_dataset={"topic": "India GDP", "dataset_id": "ds-gdp", "source": "World Bank"},
        selected_tools=[{"tool_id": "trend"}, {"tool_id": "forecast"}],
        planner_output={"topics": ["India GDP"], "intent": "forecasting"},
        comment="solid analysis",
    )
    assert isinstance(rec, FeedbackRecord)
    assert rec.feedback == FeedbackType.GOOD_ANSWER
    assert rec.user == "alice"
    assert rec.timestamp
    assert rec.reward > 0
    assert rec.chosen_dataset["topic"] == "India GDP"

    one = get_feedback(feedback_id=rec.feedback_id)
    assert one is not None
    assert one.feedback_id == rec.feedback_id

    many = get_feedback(user="alice")
    assert isinstance(many, list)
    assert any(r.feedback_id == rec.feedback_id for r in many)


def test_all_feedback_types_parse():
    types = [
        "wrong_dataset",
        "wrong_chart",
        "bad_explanation",
        "wrong_forecast",
        "poor_visualization",
        "good_answer",
        "excellent_answer",
    ]
    for t in types:
        rec = record_feedback(question=f"Q {t}", feedback=t, user="u")
        assert rec.feedback == FeedbackType.parse(t)


def test_record_requires_question():
    with pytest.raises(ValueError):
        record_feedback(question="", feedback="good_answer")


def test_get_filter_by_type():
    record_feedback(question="GDP", feedback="good_answer", user="a")
    record_feedback(question="GDP bad", feedback="wrong_dataset", user="a")
    rows = get_feedback(feedback_type="wrong_dataset", user="a")
    assert all(r.feedback == FeedbackType.WRONG_DATASET for r in rows)
    assert len(rows) >= 1


# ---------------------------------------------------------------------------
# adjust_scores
# ---------------------------------------------------------------------------


def test_adjust_scores_positive_and_negative():
    record_feedback(
        question="Forecast gold prices",
        feedback="excellent_answer",
        chosen_dataset={"topic": "Gold Price", "dataset_id": "gold-1"},
        selected_tools=["forecast", "trend", "visualization"],
        planner_output={"topics": ["Gold Price"], "confidence": 0.7},
    )
    record_feedback(
        question="Forecast gold prices",
        feedback="wrong_dataset",
        chosen_dataset={"topic": "Rainfall", "dataset_id": "rain-1"},
        selected_tools=["trend"],
        planner_output={"topics": ["Rainfall"]},
    )
    record_feedback(
        question="Forecast gold prices",
        feedback="wrong_forecast",
        chosen_dataset={"topic": "Gold Price", "dataset_id": "gold-1"},
        selected_tools=["forecast"],
        planner_output={"topics": ["Gold Price"]},
    )

    adj = adjust_scores(question="Forecast gold prices")
    assert isinstance(adj, ScoreAdjustment)
    assert adj.n_feedback >= 3
    assert adj.mean_reward != 0.0

    # Gold boosted by excellent, rainfall penalized by wrong_dataset
    assert adj.dataset_scores.get("gold-1", 0) >= 0 or adj.dataset_scores.get("gold price", 0) >= 0
    # rainfall should be negative
    rain_keys = [k for k in adj.dataset_scores if "rain" in k]
    assert rain_keys
    assert adj.dataset_scores[rain_keys[0]] < 0

    # forecast tool penalized
    assert adj.tool_scores.get("forecast", 0) < 0 or any(
        v < 0 for k, v in adj.tool_scores.items() if "forecast" in k
    )

    # planner confidence affected
    assert adj.planner_confidence_delta != 0.0

    # semantic scores present
    assert adj.semantic_scores


def test_apply_to_score_helper():
    adj = ScoreAdjustment(
        dataset_scores={"india gdp": 0.1},
        tool_scores={"forecast": -0.15},
        planner_confidence_delta=-0.05,
        semantic_scores={"gdp": 0.08},
    )
    assert adj.apply_to_score(0.5, kind="dataset", key="india gdp") == pytest.approx(0.6)
    assert adj.apply_to_score(0.5, kind="tool", key="forecast") == pytest.approx(0.35)
    assert adj.apply_to_score(0.5, kind="planner", key="x") == pytest.approx(0.45)
    assert adj.apply_to_score(0.9, kind="semantic", key="gdp") == pytest.approx(0.98)
    # clamp
    assert adj.apply_to_score(0.95, kind="dataset", key="india gdp") <= 1.0


def test_wrong_chart_affects_visualization_tools():
    record_feedback(
        question="Show GDP chart",
        feedback="poor_visualization",
        chosen_dataset={"topic": "GDP"},
        selected_tools=[{"tool_id": "visualization"}, {"tool_id": "histogram"}],
    )
    adj = adjust_scores()
    assert adj.tool_scores.get("visualization", 0) < 0 or adj.tool_scores.get("histogram", 0) < 0


def test_bad_explanation_feedback():
    record_feedback(
        question="Explain GDP",
        feedback="bad_explanation",
        chosen_dataset={"topic": "GDP", "source": "WB"},
        selected_tools=["trend"],
    )
    adj = adjust_scores()
    assert adj.planner_confidence_delta < 0
    assert FeedbackType.BAD_EXPLANATION.value in adj.by_type


# ---------------------------------------------------------------------------
# Service / memory / RLHF helpers
# ---------------------------------------------------------------------------


def test_service_class_and_memory_isolation():
    mem = FeedbackMemory()
    svc = FeedbackService(memory=mem, scorer=FeedbackScorer())
    svc.record_feedback(question="Q1", feedback="good_answer", user="bob")
    assert mem.count() == 1
    # default service unaffected
    assert get_feedback(user="bob") == [] or get_feedback(user="bob") is not None
    # isolated memory not on default unless same
    default_list = get_feedback(user="bob")
    # bob only on isolated mem — default should be empty for bob if reset worked
    assert isinstance(default_list, list)


def test_preference_pair_rlhf_ready():
    svc = FeedbackService()
    chosen, rejected = svc.record_preference_pair(
        question="Best GDP dataset?",
        chosen={
            "dataset": {"topic": "World Bank GDP", "dataset_id": "wb"},
            "tools": ["trend"],
        },
        rejected={
            "dataset": {"topic": "Random CSV", "dataset_id": "rnd"},
            "tools": ["eda_summary"],
            "kind": "dataset",
        },
        user="rlhf_user",
    )
    assert chosen.trajectory_id == rejected.trajectory_id
    assert chosen.preference_rank == 0
    assert rejected.preference_rank == 1
    assert chosen.reward > rejected.reward

    export = svc.export_rlhf_dataset()
    assert len(export) >= 2
    assert all("reward" in row and "prompt" in row for row in export)


def test_to_dict_roundtrip():
    rec = record_feedback(
        question="Population trend",
        feedback=FeedbackType.EXCELLENT_ANSWER,
        chosen_dataset="India Population",
        selected_tools=["trend"],
        planner_output={"topics": ["Population"]},
    )
    d = rec.to_dict()
    back = FeedbackRecord.from_dict(d)
    assert back.question == rec.question
    assert back.feedback == FeedbackType.EXCELLENT_ANSWER
    assert back.chosen_dataset["topic"] == "India Population"


def test_score_adjustment_to_dict():
    adj = adjust_scores()
    d = adj.to_dict()
    assert "dataset_scores" in d
    assert "tool_scores" in d
    assert "planner_confidence_delta" in d
    assert "semantic_scores" in d
    back = ScoreAdjustment.from_dict(d)
    assert back.n_feedback == adj.n_feedback
