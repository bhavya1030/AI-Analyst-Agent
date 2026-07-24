"""Tests for Dataset Learning Service."""

from backend.learning import LearningAction, learn_dataset
from backend.registry import delete_dataset, get_by_dataset_id, list_datasets


def _cleanup_topic(topic: str):
    for row in list_datasets(limit=100):
        if row.topic == topic or topic in (row.topic or ""):
            delete_dataset(row.dataset_id)


def test_learn_creates_new_registry_entry():
    topic = "learning_test_gold_unique_xyz"
    _cleanup_topic(topic)

    retrieval = {
        "status": "INTERNET_HIT",
        "download_url": "https://example.com/learning_gold.csv",
        "provider": "internet_search:GitHub",
        "topic": topic,
        "metadata": {
            "title": "Learning Gold CSV",
            "source": "GitHub",
            "source_type": "GitHub",
            "description": "test gold series",
        },
    }
    acquisition = {
        "success": True,
        "local_path": "/tmp/learning_gold.csv",
        "checksum": "aaa111checksum",
        "detected_format": "csv",
        "dataset_id": None,
        "source_url": "https://example.com/learning_gold.csv",
        "provider": "internet_search:GitHub",
    }
    profile = {
        "dataset_type": "time_series",
        "row_count": 100,
        "column_names": ["Date", "Price"],
        "time_column": "Date",
        "entity_column": None,
        "numeric_metrics": ["Price"],
        "categorical_fields": [],
        "date_range": {"start": "2000", "end": "2024"},
        "countries_regions": [],
        "topic_keywords": ["gold", "price"],
        "domain": "finance",
        "file_format": "csv",
        "local_path": "/tmp/learning_gold.csv",
    }

    result = learn_dataset(
        retrieval=retrieval,
        acquisition=acquisition,
        profile=profile,
    )
    assert result.action_taken == LearningAction.CREATED
    assert result.created is True
    assert result.updated is False
    assert result.duplicate_detected is False
    assert result.registry_id

    row = get_by_dataset_id(result.registry_id)
    assert row is not None
    assert row.topic == topic
    assert row.checksum == "aaa111checksum"
    assert row.local_path == "/tmp/learning_gold.csv"
    assert row.row_count == 100
    assert "Date" in (row.columns or [])
    assert "finance" in (row.tags or []) or "gold" in (row.tags or [])
    assert row.usage_count == 1
    assert row.date_range == {"start": "2000", "end": "2024"}

    delete_dataset(result.registry_id)


def test_learn_updates_duplicate_by_checksum():
    topic = "learning_test_dup_unique_xyz"
    _cleanup_topic(topic)

    base = {
        "retrieval": {
            "status": "API_HIT",
            "download_url": "https://example.com/dup.csv",
            "topic": topic,
            "metadata": {"title": "Dup Dataset", "source": "World Bank", "source_type": "API"},
        },
        "acquisition": {
            "success": True,
            "local_path": "/tmp/dup_v1.csv",
            "checksum": "dup-checksum-999",
            "detected_format": "csv",
            "source_url": "https://example.com/dup.csv",
        },
        "profile": {
            "dataset_type": "tabular",
            "row_count": 10,
            "column_names": ["A", "B"],
            "domain": "economics",
            "topic_keywords": ["gdp"],
            "file_format": "csv",
        },
    }
    first = learn_dataset(**base)
    assert first.created is True
    rid = first.registry_id

    # Same checksum, new path / usage
    base["acquisition"] = {
        "success": True,
        "local_path": "/tmp/dup_v2.csv",
        "checksum": "dup-checksum-999",
        "detected_format": "csv",
        "source_url": "https://example.com/dup.csv",
    }
    base["profile"]["row_count"] = 12
    second = learn_dataset(**base)
    assert second.updated is True
    assert second.duplicate_detected is True
    assert second.registry_id == rid

    row = get_by_dataset_id(rid)
    assert row is not None
    assert row.local_path == "/tmp/dup_v2.csv"
    assert row.usage_count >= 2
    assert row.row_count == 12

    delete_dataset(rid)


def test_learn_skips_failed_acquisition():
    result = learn_dataset(
        retrieval={"topic": "x", "download_url": "https://example.com/x.csv"},
        acquisition={"success": False, "errors": ["download failed"]},
        profile={"dataset_type": "tabular", "column_names": []},
    )
    assert result.action_taken == LearningAction.SKIPPED
