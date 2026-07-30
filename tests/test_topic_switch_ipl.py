"""GDP → IPL → Gold → Population → GDP topic switch regression."""

from __future__ import annotations

from backend.main import _build_state
from backend.memory.continuity import should_reuse_session_dataset
from backend.memory.topic_switch import (
    detect_topic_switch,
    release_bound_file_if_topic_switch,
)


class _FakeSession:
    def __init__(self, topic="India GDP", path="/data/local_library/india_gdp.csv"):
        self.dataset_topic = topic
        self.dataset_name = topic
        self.dataset_path = path
        self.dataset_url = None
        self.last_column = None
        self.last_columns = []
        self.last_chart_type = None
        self.last_intent = None
        self.last_operation = None
        self.last_forecast_target = None
        self.eda_summary = None


def test_detect_ipl_after_gdp():
    assert detect_topic_switch(
        "Analyze IPL",
        dataset_topic="India GDP",
        dataset_name="india_gdp.csv",
        dataset_path="/data/india_gdp.csv",
        file_path="/data/india_gdp.csv",
        has_active_dataset=True,
    )


def test_release_file_path_on_ipl():
    path, switch = release_bound_file_if_topic_switch(
        "Analyze IPL",
        "/data/local_library/india_gdp.csv",
        session_topic="India GDP",
        session_name="india_gdp.csv",
        session_path="/data/local_library/india_gdp.csv",
    )
    assert switch is True
    assert path is None


def test_keep_file_on_follow_up_histogram():
    path, switch = release_bound_file_if_topic_switch(
        "Show histogram",
        "/data/local_library/india_gdp.csv",
        session_topic="India GDP",
        session_path="/data/local_library/india_gdp.csv",
    )
    assert switch is False
    assert path == "/data/local_library/india_gdp.csv"


def test_should_reuse_mismatch_with_override_path():
    reuse, mismatch = should_reuse_session_dataset(
        question="Analyze IPL",
        dataset_topic="India GDP",
        dataset_path="/data/india_gdp.csv",
        dataset_url=None,
        has_frame=False,
        file_path_override="/data/india_gdp.csv",
    )
    assert reuse is False
    assert mismatch is True


def test_build_state_clears_gdp_for_ipl():
    session = _FakeSession()
    state = _build_state(
        session,
        question="Analyze IPL",
        file_path="/data/local_library/india_gdp.csv",
    )
    assert state["topic_mismatch"] is True
    assert state["file_path"] in (None, "")
    assert state["dataset_path"] in (None, "")
    assert state["dataset_topic"] in (None, "")
    assert state["reuse_active_dataset"] is False
    assert state["force_reload_dataset"] is True
    assert state["data"] is None


def test_transition_chain():
    """GDP → IPL → Gold → Population → GDP."""
    cases = [
        ("India GDP", "/data/india_gdp.csv", "Analyze IPL", True),
        ("IPL", "/data/ipl.csv", "Analyze gold prices", True),
        ("Gold prices", "/data/gold.csv", "Analyze world population", True),
        ("Population", "/data/pop.csv", "Analyze India GDP", True),
        ("India GDP", "/data/india_gdp.csv", "Show histogram", False),
        ("India GDP", "/data/india_gdp.csv", "Forecast next 5 years", False),
    ]
    for topic, path, question, expect_switch in cases:
        reuse, mismatch = should_reuse_session_dataset(
            question=question,
            dataset_topic=topic,
            dataset_path=path,
            dataset_url=None,
            has_frame=False,
            file_path_override=path,
        )
        assert mismatch is expect_switch, f"{topic} + {question!r} → mismatch={mismatch}"
        if expect_switch:
            assert reuse is False
