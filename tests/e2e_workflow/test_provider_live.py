"""Live (network) smoke tests for provider orchestrator — skip if offline."""

from __future__ import annotations

import os

import pytest

from backend.retrieval.data_providers.orchestrator import get_provider_orchestrator
from backend.retrieval.service import set_retrieval_agent
from backend.retrieval import retrieve_dataset, RetrievalStatus

# Force rebuild of default agent with OpenDataProvider
set_retrieval_agent(None)

pytestmark = pytest.mark.skipif(
    os.environ.get("E2E_SKIP_NETWORK", "").lower() in {"1", "true", "yes"},
    reason="Network tests disabled",
)

TOPICS = [
    "world GDP open data trends",
    "world population open data growth",
    "global CO2 emissions open data",
    "renewable energy production open data",
    "global inflation rates open data",
    "bitcoin cryptocurrency prices",
    "olympic medal counts open data",
    "global internet usage statistics open data",
    "international tourism arrivals open data",
    "electric vehicle sales open data",
]


@pytest.mark.parametrize("topic", TOPICS)
def test_orchestrator_resolves_topic(topic: str):
    orch = get_provider_orchestrator()
    result = orch.resolve(topic)
    assert result.success, f"{topic}: {result.failure_reason} attempts={result.attempts[-3:]}"
    assert result.candidate and result.candidate.download_url
    assert "searchresults" not in result.candidate.download_url
    assert "wikipedia.org" not in result.candidate.download_url


@pytest.mark.parametrize("topic", TOPICS[:5])
def test_retrieve_dataset_open_data_hit(topic: str):
    set_retrieval_agent(None)
    result = retrieve_dataset({"topic": topic, "force_new_topic": True})
    assert result.status in {
        RetrievalStatus.API_HIT,
        RetrievalStatus.INTERNET_HIT,
        RetrievalStatus.REGISTRY_HIT,
        RetrievalStatus.SEMANTIC_HIT,
        RetrievalStatus.STALE_REGISTRY_ENTRY,
    }, f"{topic} -> {result.status} {result.reason}"
    assert result.download_url or result.local_path
    if result.download_url:
        assert "searchresults" not in result.download_url
