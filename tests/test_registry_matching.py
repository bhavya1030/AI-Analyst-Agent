"""Tests for high-confidence Dataset Registry matching."""

from __future__ import annotations

from backend.registry.matching import (
    build_match_query,
    match_registry,
    score_dataset,
)
from backend.registry.models import DatasetMetadata, new_dataset_id
from backend.retrieval.providers.registry_provider import RegistryProvider
from backend.retrieval.models import DatasetRequest, RetrievalStatus


def _meta(**kwargs) -> DatasetMetadata:
    base = {
        "dataset_id": new_dataset_id(),
        "title": kwargs.pop("title", "Dataset"),
        "topic": kwargs.pop("topic", "general"),
        "download_url": kwargs.pop("download_url", "https://example.com/d.csv"),
        "is_active": True,
    }
    base.update(kwargs)
    return DatasetMetadata.from_dict(base)


def test_olympics_does_not_match_gdp():
    gdp = _meta(
        title="World Bank GDP",
        topic="gdp atlantis",  # polluted historical topic
        domain="macroeconomics",
        keywords=["gdp", "macro", "country", "year"],
        columns=["Country Name", "Country Code", "Year", "Value"],
        tags=["gdp", "macro"],
    )
    query = build_match_query("olympic medal counts by country")
    score = score_dataset(query, gdp)
    assert not score.accepted
    assert score.confidence < 0.62
    assert any(
        "conflict" in r.lower() or "sports" in r.lower() or "olympic" in r.lower()
        for r in score.rejections + [score.explanation]
    )


def test_atlantis_does_not_match_world_bank_gdp():
    gdp = _meta(
        title="World Bank GDP (open CSV)",
        topic="world gdp",
        domain="macroeconomics",
        keywords=["gdp", "world bank"],
        columns=["Country Name", "Year", "Value"],
    )
    score = score_dataset(build_match_query("Analyze GDP of Atlantis"), gdp)
    assert not score.accepted
    assert "fictional" in score.explanation.lower() or any(
        "fictional" in r.lower() for r in score.rejections
    )


def test_unicorn_population_rejected():
    pop = _meta(
        title="World Population",
        topic="population unicorn worldwide",
        domain="demographics",
        keywords=["population", "demographics"],
        columns=["Country Name", "Year", "Value"],
    )
    score = score_dataset(build_match_query("Analyze Unicorn Population worldwide"), pop)
    assert not score.accepted


def test_exact_gdp_match_accepted():
    gdp = _meta(
        title="World Bank GDP",
        topic="world gdp",
        domain="macroeconomics",
        keywords=["gdp", "macro", "country"],
        columns=["Country Name", "Year", "Value"],
        tags=["gdp", "macro"],
    )
    score = score_dataset(build_match_query("world gdp open data trends"), gdp)
    assert score.accepted
    assert score.confidence >= 0.62
    assert "confidence" in score.explanation.lower() or score.reasons


def test_population_matches_population_not_olympics():
    pop = _meta(
        title="World Population",
        topic="world population",
        domain="demographics",
        keywords=["population"],
        columns=["Country Name", "Year", "Value"],
    )
    olympics = _meta(
        title="Olympics medals",
        topic="olympic medals",
        domain="sports",
        keywords=["olympic", "medal"],
        columns=["Year", "City", "Sport", "Medal", "Country"],
    )
    hits = match_registry(
        "world population growth open data",
        [pop, olympics],
        min_confidence=0.55,
    )
    assert hits
    assert hits[0].dataset_id == pop.dataset_id
    assert hits[0].metadata.domain == "demographics"


def test_match_registry_returns_empty_for_low_confidence():
    gdp = _meta(
        title="GDP",
        topic="gdp",
        domain="macroeconomics",
        keywords=["gdp"],
        columns=["Year", "Value"],
    )
    hits = match_registry("dragon population trends", [gdp])
    assert hits == []


def test_registry_provider_skips_low_confidence():
    gdp = _meta(
        title="World Bank GDP",
        topic="gdp",
        domain="macroeconomics",
        keywords=["gdp"],
        columns=["Year", "Value", "Country Name"],
        local_path=None,
        download_url="https://example.com/gdp.csv",
    )

    def get_by_topic(topic, limit=10):
        return [gdp]

    provider = RegistryProvider(
        get_by_topic=get_by_topic,
        dataset_exists=lambda _id: False,
        get_dataset_path=lambda _id: None,
    )
    hit = provider.try_retrieve(
        DatasetRequest(topic="olympic medal counts by country")
    )
    assert hit is None  # must fall through to internet retrieval


def test_registry_provider_accepts_good_match(tmp_path):
    path = tmp_path / "gdp.csv"
    path.write_text("Country,Year,Value\nIndia,2020,1\n", encoding="utf-8")
    gdp = _meta(
        title="World Bank GDP",
        topic="india gdp",
        domain="macroeconomics",
        keywords=["gdp", "india"],
        columns=["Country", "Year", "Value"],
        tags=["gdp"],
        local_path=str(path),
        download_url="https://example.com/gdp.csv",
    )

    provider = RegistryProvider(
        get_by_topic=lambda topic, limit=10: [gdp],
        dataset_exists=lambda _id: True,
        get_dataset_path=lambda _id: str(path),
    )
    hit = provider.try_retrieve(DatasetRequest(topic="india gdp trend analysis"))
    assert hit is not None
    assert hit.status == RetrievalStatus.REGISTRY_HIT
    assert hit.metadata.get("match_confidence", 0) >= 0.55
    assert hit.metadata.get("match_explanation")
    assert "confidence" in (hit.reason or "").lower() or hit.metadata.get("match_reasons")


def test_build_match_query_domain_for_olympics():
    q = build_match_query("Analyze Olympic medal counts by country")
    assert q.domain == "sports"
    assert "olympics" in q.aliases or "olympic" in q.keywords or "medal" in q.keywords
