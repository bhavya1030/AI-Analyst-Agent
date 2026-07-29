"""Unit tests for Dataset Retrieval Agent (no internet, no LangGraph)."""

from backend.dataset_library import LocalFilesystemStorage, set_default_storage
from backend.dataset_library.service import DatasetLibraryService
from backend.registry import delete_dataset, insert_dataset
from backend.retrieval import (
    DatasetRequest,
    DatasetRetrievalAgent,
    NextAction,
    RetrievalStatus,
    retrieve_dataset,
)
from backend.retrieval.providers.registry_provider import RegistryProvider
from backend.retrieval.providers.session_provider import SessionProvider
from backend.retrieval.service import set_retrieval_agent


def _agent_with(session_provider=None, registry_provider=None):
    providers = []
    if session_provider:
        providers.append(session_provider)
    if registry_provider:
        providers.append(registry_provider)
    return DatasetRetrievalAgent(providers=providers)


def test_session_hit():
    agent = _agent_with(
        session_provider=SessionProvider(),
        registry_provider=RegistryProvider(get_by_topic=lambda topic, limit=10: []),
    )
    result = agent.retrieve(
        {
            "topic": "India GDP",
            "session_topic": "india gdp",
            "session_dataset_url": "https://example.com/gdp.csv",
            "has_active_data": True,
        }
    )
    assert result.status == RetrievalStatus.SESSION_HIT
    assert result.next_action == NextAction.USE_SESSION
    assert result.download_url.endswith("gdp.csv")


def test_session_miss_forces_registry():
    agent = _agent_with(
        session_provider=SessionProvider(),
        registry_provider=RegistryProvider(get_by_topic=lambda topic, limit=10: []),
    )
    result = agent.retrieve(
        {
            "topic": "gold price",
            "session_topic": "india gdp",
            "has_active_data": True,
            "session_dataset_url": "https://example.com/gdp.csv",
        }
    )
    # Topics incompatible → session returns None → SEARCH_REQUIRED
    assert result.status == RetrievalStatus.SEARCH_REQUIRED
    assert result.next_action == NextAction.RUN_INTERNET_SEARCH


def test_registry_hit_with_library_file(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "datasets")
    set_default_storage(storage)
    lib = DatasetLibraryService(storage)

    reg = insert_dataset(
        {
            "title": "Gold Annual",
            "topic": "gold price",
            "download_url": "https://example.com/gold.csv",
            "source": "test",
            "source_type": "GitHub",
            "file_format": "csv",
        }
    )
    lib.save_dataset(
        dataset_id=reg.dataset_id,
        data=b"Date,Price\n2020,1\n",
        source="test",
        topic="gold price",
        file_format="csv",
    )

    from backend.dataset_library import dataset_exists, get_dataset_path
    from backend.registry import get_by_topic

    agent = _agent_with(
        session_provider=SessionProvider(),
        registry_provider=RegistryProvider(
            get_by_topic=get_by_topic,
            dataset_exists=dataset_exists,
            get_dataset_path=get_dataset_path,
        ),
    )
    result = agent.retrieve({"topic": "gold price", "force_new_topic": True})
    assert result.status == RetrievalStatus.REGISTRY_HIT
    assert result.dataset_id == reg.dataset_id
    assert result.local_path
    assert result.next_action == NextAction.USE_LOCAL_FILE

    delete_dataset(reg.dataset_id)
    lib.delete_dataset(reg.dataset_id)


def test_stale_registry_entry():
    from backend.dataset_library import dataset_exists, get_dataset_path
    from backend.registry import get_by_topic, list_datasets

    # Clean leftover avocado rows from prior runs so confidence matching is deterministic
    for row in list_datasets(limit=200):
        if (row.topic or "").lower() == "avocado prices":
            delete_dataset(row.dataset_id)

    reg = insert_dataset(
        {
            "title": "Missing Local",
            "topic": "avocado prices",
            "download_url": "https://example.com/avo.csv",
            "local_path": "/nonexistent/path/avo.csv",
            "source": "test",
            "file_format": "csv",
            "keywords": ["avocado", "prices"],
            "domain": "general",
        }
    )

    agent = _agent_with(
        session_provider=SessionProvider(),
        registry_provider=RegistryProvider(
            get_by_topic=get_by_topic,
            dataset_exists=dataset_exists,
            get_dataset_path=get_dataset_path,
        ),
    )
    result = agent.retrieve({"topic": "avocado prices", "force_new_topic": True})
    assert result.status == RetrievalStatus.STALE_REGISTRY_ENTRY
    assert result.dataset_id == reg.dataset_id
    assert result.metadata is None or result.metadata.get("match_confidence", 1) >= 0.55

    delete_dataset(reg.dataset_id)


def test_search_required_when_empty():
    agent = _agent_with(
        session_provider=SessionProvider(),
        registry_provider=RegistryProvider(get_by_topic=lambda topic, limit=10: []),
    )
    result = agent.retrieve(DatasetRequest(topic="completely unknown topic xyz"))
    assert result.status == RetrievalStatus.SEARCH_REQUIRED
    assert result.next_action == NextAction.RUN_INTERNET_SEARCH
