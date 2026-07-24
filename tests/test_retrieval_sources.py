"""Tests for open-data source connectors + providers."""

from backend.retrieval import DatasetRetrievalAgent, RetrievalStatus
from backend.retrieval.providers.official_api_provider import OfficialApiProvider
from backend.retrieval.providers.internet_search_provider import InternetSearchProvider
from backend.retrieval.providers.session_provider import SessionProvider
from backend.retrieval.providers.registry_provider import RegistryProvider
from backend.retrieval.sources.github import GitHubSource
from backend.retrieval.sources.world_bank import WorldBankSource


def test_github_source_gold():
    hits = GitHubSource().search("gold rate", limit=3)
    assert hits
    assert hits[0].download_url and "gold" in hits[0].download_url.lower()
    assert hits[0].source_type == "GitHub"


def test_world_bank_source_gdp():
    hits = WorldBankSource().search("India GDP", limit=3)
    assert hits
    assert any("gdp" in (h.title + (h.download_url or "")).lower() for h in hits)


def test_official_provider_gdp():
    from backend.retrieval.models import DatasetRequest

    provider = OfficialApiProvider()
    hit = provider.try_retrieve(DatasetRequest(topic="world gdp"))
    assert hit is not None
    assert hit.status == RetrievalStatus.API_HIT
    assert hit.download_url


def test_internet_provider_gold():
    from backend.retrieval.models import DatasetRequest

    provider = InternetSearchProvider(sources=[GitHubSource()])
    hit = provider.try_retrieve(DatasetRequest(topic="gold price"))
    assert hit is not None
    assert hit.status == RetrievalStatus.INTERNET_HIT
    assert hit.download_url


def test_full_agent_priority_internet_after_miss():
    from backend.retrieval.models import DatasetRequest

    agent = DatasetRetrievalAgent(
        providers=[
            SessionProvider(),
            RegistryProvider(get_by_topic=lambda topic, limit=10: []),
            OfficialApiProvider(sources=[]),  # force skip official
            InternetSearchProvider(sources=[GitHubSource()]),
        ]
    )
    result = agent.retrieve(DatasetRequest(topic="gold rate", force_new_topic=True))
    assert result.status == RetrievalStatus.INTERNET_HIT
    assert result.download_url
