"""Tests for Dataset Selection module."""

from backend.dataset_selection import (
    DatasetCandidate,
    LLMDatasetSelector,
    RuleBasedSelector,
    select_best_dataset,
)


def test_rule_based_picks_matching_topic():
    candidates = [
        {
            "dataset_id": "weather-1",
            "title": "Global Temperature",
            "topic": "climate",
            "description": "Temperature anomalies",
            "download_url": "https://example.com/temp.csv",
            "tags": ["climate", "weather"],
        },
        {
            "dataset_id": "gdp-1",
            "title": "World Bank GDP",
            "topic": "gdp",
            "description": "Gross Domestic Product by country",
            "download_url": "https://example.com/gdp.csv",
            "tags": ["gdp", "economy"],
            "rank_hint": 10,
        },
    ]
    result = select_best_dataset(
        "Analyze India's GDP growth",
        candidates,
        topic="india gdp",
    )
    assert result.best_dataset is not None
    assert result.best_dataset.candidate_id == "gdp-1"
    assert 0.0 <= result.confidence <= 1.0
    assert result.reason
    assert result.selector == "rule_based"


def test_prefers_semantic_score_and_local_path():
    selector = RuleBasedSelector()
    candidates = [
        DatasetCandidate(
            candidate_id="a",
            title="Maybe related",
            topic="macro",
            download_url="https://example.com/a.html",
            similarity_score=0.4,
        ),
        DatasetCandidate(
            candidate_id="b",
            title="GDP series",
            topic="gdp",
            local_path="/data/gdp.csv",
            download_url="https://example.com/gdp.csv",
            similarity_score=0.85,
            tags=["gdp"],
        ),
    ]
    result = selector.select_best_dataset("GDP economy", candidates)
    assert result.best_dataset is not None
    assert result.best_dataset.candidate_id == "b"
    assert "semantic" in result.reason.lower() or result.scores.get("b", 0) > result.scores.get("a", 0)


def test_single_candidate():
    result = select_best_dataset("anything", [{"dataset_id": "only", "title": "Only"}])
    assert result.best_dataset.candidate_id == "only"
    assert result.confidence >= 0.9


def test_empty_candidates():
    result = select_best_dataset("question", [])
    assert result.best_dataset is None
    assert result.confidence == 0.0


def test_llm_placeholder_delegates():
    result = LLMDatasetSelector().select_best_dataset(
        "gold prices",
        [
            {"dataset_id": "gold", "title": "Gold prices", "tags": ["gold"], "download_url": "https://x/g.csv"},
            {"dataset_id": "pop", "title": "Population", "tags": ["population"], "download_url": "https://x/p.csv"},
        ],
    )
    assert result.selector == "llm"
    assert result.best_dataset is not None
    assert result.best_dataset.candidate_id == "gold"
    assert "placeholder" in result.reason.lower() or "rule" in result.reason.lower()
