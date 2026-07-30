"""Unit tests for multi-provider open-data retrieval architecture."""

from __future__ import annotations

from backend.retrieval.data_providers.base import DatasetCandidate
from backend.retrieval.data_providers.catalog import catalog_entries_for
from backend.retrieval.data_providers.orchestrator import ProviderOrchestrator
from backend.retrieval.data_providers.topic import extract_topic_context
from backend.retrieval.data_providers.validation import (
    is_blocked_url,
    validate_download_payload,
)
from backend.retrieval.models import DatasetRequest, RetrievalStatus
from backend.retrieval.providers.open_data_provider import OpenDataProvider


def test_block_oecd_search_html_urls():
    blocked, reason = is_blocked_url(
        "https://data.oecd.org/searchresults/?q=vehicle+sales+electric"
    )
    assert blocked
    assert "oecd" in reason or "search" in reason or "blocked" in reason


def test_block_wikipedia_and_login():
    assert is_blocked_url("https://en.wikipedia.org/wiki/Gross_domestic_product")[0]
    assert is_blocked_url("https://example.com/login?next=/data")[0]


def test_allow_raw_github_and_world_bank_json():
    assert not is_blocked_url(
        "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv"
    )[0]
    assert not is_blocked_url(
        "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?format=json&per_page=20"
    )[0]


def test_reject_html_payload():
    html = b"<!DOCTYPE html><html><head><title>Search</title></head><body>results</body></html>"
    result = validate_download_payload(
        html,
        url="https://example.com/data",
        content_type="text/html",
    )
    assert not result.ok
    assert "html" in result.reason


def test_accept_csv_payload():
    csv = b"Country,Year,Value\nIndia,2020,1\nIndia,2021,2\n"
    result = validate_download_payload(
        csv,
        url="https://example.com/data.csv",
        content_type="text/csv",
    )
    assert result.ok
    assert result.file_format == "csv"


def test_reject_pdf_payload():
    pdf = b"%PDF-1.4 fake pdf content for test purposes"
    result = validate_download_payload(pdf, url="https://example.com/file.pdf")
    assert not result.ok
    assert "pdf" in result.reason


def test_topic_aliases_cover_e2e_topics():
    cases = {
        "Analyze electric vehicle sales worldwide": "electric_vehicles",
        "global CO2 emissions over time": "co2_emissions",
        "renewable energy production": "renewable_energy",
        "World Happiness Index scores": "happiness",
        "Air Quality Index major cities": "air_quality",
        "global inflation rates": "inflation",
        "cryptocurrency prices for Bitcoin": "cryptocurrency",
        "Olympic medal counts by country": "olympics",
        "global internet usage statistics": "internet_usage",
        "international tourism arrivals": "tourism",
    }
    for text, alias in cases.items():
        ctx = extract_topic_context(text)
        assert alias in ctx.aliases, f"{text} -> {ctx.aliases}"


def test_catalog_has_downloadable_entries_for_aliases():
    aliases = [
        "gdp",
        "population",
        "co2_emissions",
        "renewable_energy",
        "electric_vehicles",
        "inflation",
        "cryptocurrency",
        "olympics",
        "internet_usage",
        "tourism",
        "happiness",
        "air_quality",
    ]
    for alias in aliases:
        entries = catalog_entries_for([alias], [])
        assert entries, f"missing catalog for {alias}"
        for e in entries:
            assert e.get("download_url")
            assert "searchresults" not in e["download_url"]
            assert "wikipedia.org" not in e["download_url"]


class _FakeProvider:
    name = "fake"
    priority = 100

    def __init__(self, candidates):
        self._candidates = candidates

    def supports(self, topic, keywords):
        return True

    def preferred_for(self, topic, keywords):
        return self.priority

    def search(self, topic, keywords, *, limit=5):
        return self._candidates[:limit]


def test_orchestrator_retries_blocked_then_succeeds(monkeypatch):
    bad = DatasetCandidate(
        title="OECD search",
        topic="ev",
        download_url="https://data.oecd.org/searchresults/?q=ev",
        provider="fake",
        rank=10,
    )
    good = DatasetCandidate(
        title="GDP CSV",
        topic="ev",
        download_url="https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
        provider="fake",
        file_format="csv",
        rank=5,
    )
    orch = ProviderOrchestrator(providers=[_FakeProvider([bad, good])], validate=True)

    from backend.retrieval.data_providers import validation as val_mod

    def fake_probe(url, **kwargs):
        from backend.retrieval.data_providers.validation import ValidationResult

        if "searchresults" in url:
            return ValidationResult(ok=False, reason="blocked_path:/searchresults", final_url=url)
        return ValidationResult(
            ok=True,
            reason="payload_ok",
            final_url=url,
            file_format="csv",
            status_code=200,
            content_type="text/csv",
        )

    monkeypatch.setattr(val_mod, "probe_download", fake_probe)
    # orchestrator imports probe_download into its namespace
    import backend.retrieval.data_providers.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "probe_download", fake_probe)

    result = orch.resolve("electric vehicle sales")
    assert result.success
    assert result.candidate is not None
    assert "searchresults" not in result.candidate.download_url
    assert result.retry_count >= 1


def test_open_data_provider_hit(monkeypatch):
    good = DatasetCandidate(
        title="Pop CSV",
        topic="population",
        download_url="https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
        provider="world_bank",
        license="CC-BY",
        dataset_version="v1",
        file_format="csv",
        rank=100,
    )
    orch = ProviderOrchestrator(providers=[_FakeProvider([good])], validate=False)
    provider = OpenDataProvider(orchestrator=orch)
    hit = provider.try_retrieve(DatasetRequest(topic="world population growth"))
    assert hit is not None
    assert hit.status in {RetrievalStatus.API_HIT, RetrievalStatus.INTERNET_HIT}
    assert hit.download_url.endswith("population.csv")
    assert hit.metadata.get("license") == "CC-BY"
    assert hit.metadata.get("provider") == "world_bank"
