"""Tests for Semantic Dataset Search (hash embeddings — no model download)."""

from backend.semantic import (
    HashingEmbeddingGenerator,
    NumpyVectorStore,
    SemanticSearchService,
    build_index_text,
)
from backend.semantic.service import set_semantic_service


def test_build_index_text_includes_fields():
    text = build_index_text(
        title="World GDP",
        description="Gross Domestic Product by country",
        tags=["gdp", "macro"],
        topic_keywords=["economy", "growth"],
        summary="Annual GDP",
        topic="gdp",
    )
    low = text.lower()
    assert "gdp" in low
    assert "gross domestic product" in low
    assert "economy" in low


def test_index_and_semantic_search(tmp_path):
    embedder = HashingEmbeddingGenerator(dimension=64)
    store = NumpyVectorStore(tmp_path / "idx.pkl", dimension=64)
    service = SemanticSearchService(embedder=embedder, store=store, auto_persist=True)
    set_semantic_service(service)

    service.index_dataset(
        {
            "dataset_id": "reg-gdp-1",
            "title": "World Bank GDP",
            "topic": "gdp",
            "description": "Gross Domestic Product national accounts",
            "tags": ["gdp", "economics"],
            "topic_keywords": ["economy", "growth"],
            "summary": "Country GDP time series",
            "source": "World Bank",
        }
    )
    service.index_dataset(
        {
            "dataset_id": "reg-weather-1",
            "title": "Global Temperature",
            "topic": "climate",
            "description": "Annual temperature anomalies",
            "tags": ["climate", "temperature"],
            "summary": "Weather and climate measurements",
            "source": "GitHub",
        }
    )

    # Related economic queries should rank GDP above weather
    hits = service.search_similar("Indian economy GDP growth", top_k=2, min_score=0.0)
    assert hits
    assert hits[0].registry_id == "reg-gdp-1"
    assert isinstance(hits[0].similarity_score, float)
    assert hits[0].metadata.get("title") == "World Bank GDP"

    # Update then search
    service.update_dataset(
        {
            "dataset_id": "reg-gdp-1",
            "title": "World Bank GDP Revised",
            "topic": "gross domestic product",
            "description": "GDP growth national income",
            "tags": ["gdp"],
            "summary": "GDP",
        }
    )
    hits2 = service.search_similar("gross domestic product", top_k=1, min_score=0.0)
    assert hits2[0].registry_id == "reg-gdp-1"

    assert service.delete_dataset("reg-weather-1") is True
    assert service.delete_dataset("reg-weather-1") is False

    set_semantic_service(None)
