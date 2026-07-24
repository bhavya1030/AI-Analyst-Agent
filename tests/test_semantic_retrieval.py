"""Semantic provider integrated into Retrieval priority."""

from backend.retrieval import DatasetRetrievalAgent, RetrievalStatus
from backend.retrieval.models import DatasetRequest
from backend.retrieval.providers.official_api_provider import OfficialApiProvider
from backend.retrieval.providers.registry_provider import RegistryProvider
from backend.retrieval.providers.semantic_provider import SemanticProvider
from backend.retrieval.providers.session_provider import SessionProvider
from backend.semantic import (
    HashingEmbeddingGenerator,
    NumpyVectorStore,
    SemanticSearchService,
)
from backend.semantic.models import SemanticSearchResult


class _FakeHit:
    def __init__(self, registry_id, score, metadata=None):
        self.registry_id = registry_id
        self.similarity_score = score
        self.metadata = metadata or {}


def test_semantic_hit_when_registry_exact_misses():
    def search_similar(query, top_k=5, min_score=0.0):
        return [
            _FakeHit(
                "reg-gdp-sem",
                0.82,
                {
                    "title": "World GDP",
                    "topic": "gdp",
                    "download_url": "https://example.com/gdp.csv",
                },
            )
        ]

    def get_by_dataset_id(rid):
        if rid == "reg-gdp-sem":
            return {
                "dataset_id": "reg-gdp-sem",
                "title": "World GDP",
                "topic": "gdp",
                "download_url": "https://example.com/gdp.csv",
                "source": "World Bank",
                "local_path": None,
            }
        return None

    agent = DatasetRetrievalAgent(
        providers=[
            SessionProvider(),
            RegistryProvider(get_by_topic=lambda topic, limit=10: []),
            SemanticProvider(
                search_similar=search_similar,
                get_by_dataset_id=get_by_dataset_id,
                dataset_exists=lambda _id: False,
                get_dataset_path=lambda _id: None,
                top_k=5,
                min_score=0.35,
            ),
            # Would match GDP via API — must NOT run if semantic hits
            OfficialApiProvider(),
        ]
    )
    result = agent.retrieve(
        DatasetRequest(topic="Indian economy growth", force_new_topic=True)
    )
    assert result.status == RetrievalStatus.SEMANTIC_HIT
    assert result.dataset_id == "reg-gdp-sem"
    assert result.download_url.endswith("gdp.csv")
    assert result.metadata.get("similarity_score", 0) >= 0.35


def test_semantic_below_threshold_continues_to_api():
    def search_similar(query, top_k=5, min_score=0.0):
        return [_FakeHit("reg-weak", 0.10, {"title": "noise", "download_url": "https://x"})]

    agent = DatasetRetrievalAgent(
        providers=[
            SessionProvider(),
            RegistryProvider(get_by_topic=lambda topic, limit=10: []),
            SemanticProvider(
                search_similar=search_similar,
                get_by_dataset_id=lambda rid: {"dataset_id": rid, "download_url": "https://x"},
                min_score=0.35,
            ),
            OfficialApiProvider(),  # should win for GDP
        ]
    )
    result = agent.retrieve(DatasetRequest(topic="world gdp", force_new_topic=True))
    assert result.status == RetrievalStatus.API_HIT
    assert result.download_url


def test_semantic_with_real_index_hash_embeddings(tmp_path):
    embedder = HashingEmbeddingGenerator(dimension=64)
    store = NumpyVectorStore(tmp_path / "sem.pkl", dimension=64)
    sem = SemanticSearchService(embedder=embedder, store=store, auto_persist=False)
    sem.index_dataset(
        {
            "dataset_id": "reg-gdp-real",
            "title": "Gross Domestic Product",
            "topic": "gdp",
            "description": "National GDP growth economy India",
            "tags": ["gdp", "economics", "india", "economy"],
            "summary": "GDP economy growth time series",
            "download_url": "https://example.com/gdp.csv",
        }
    )

    agent = DatasetRetrievalAgent(
        providers=[
            SessionProvider(),
            RegistryProvider(get_by_topic=lambda topic, limit=10: []),
            SemanticProvider(
                search_similar=sem.search_similar,
                get_by_dataset_id=lambda rid: {
                    "dataset_id": rid,
                    "title": "Gross Domestic Product",
                    "download_url": "https://example.com/gdp.csv",
                    "topic": "gdp",
                },
                dataset_exists=lambda _id: False,
                min_score=0.0,
                top_k=3,
            ),
        ]
    )
    # Shared tokens with indexed text (hash embedder)
    result = agent.retrieve(
        DatasetRequest(topic="India GDP economy growth", force_new_topic=True)
    )
    assert result.status == RetrievalStatus.SEMANTIC_HIT
    assert result.dataset_id == "reg-gdp-real"
