"""Unit tests for Dataset Registry (metadata store only)."""

from backend.registry import (
    DatasetNotFoundError,
    DatasetValidationError,
    delete_dataset,
    get_by_dataset_id,
    get_by_topic,
    increment_usage,
    insert_dataset,
    list_datasets,
    update_dataset,
    update_last_used,
)


def test_insert_and_get_by_id():
    meta = insert_dataset(
        {
            "title": "Annual Gold Prices",
            "topic": "gold price",
            "description": "Historical annual gold USD prices",
            "source": "datasets/gold-prices",
            "source_type": "GitHub",
            "download_url": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
            "file_format": "csv",
            "tags": ["gold", "commodity"],
            "columns": ["Date", "Price"],
            "row_count": 192,
            "date_range": {"start": "1833", "end": "2025"},
            "summary": "Long-run annual gold prices",
            "checksum": "abc123",
            "embedding_ref": None,
        }
    )
    assert meta.dataset_id
    assert meta.topic == "gold price"
    assert meta.usage_count == 0
    assert meta.embedding_ref is None

    fetched = get_by_dataset_id(meta.dataset_id)
    assert fetched is not None
    assert fetched.download_url.endswith("annual.csv")
    assert fetched.columns == ["Date", "Price"]

    # cleanup
    assert delete_dataset(meta.dataset_id) is True


def test_get_by_topic_and_list():
    a = insert_dataset(
        {
            "title": "GDP",
            "topic": "world gdp",
            "download_url": "https://example.com/gdp.csv",
            "file_format": "csv",
            "tags": ["gdp", "macro"],
        }
    )
    hits = get_by_topic("gdp")
    assert any(h.dataset_id == a.dataset_id for h in hits)

    listed = list_datasets(limit=50)
    assert any(h.dataset_id == a.dataset_id for h in listed)

    delete_dataset(a.dataset_id)


def test_update_increment_usage_and_last_used():
    meta = insert_dataset(
        {
            "title": "Population",
            "topic": "population",
            "download_url": "https://example.com/pop.csv",
        }
    )
    updated = update_dataset(
        {
            "dataset_id": meta.dataset_id,
            "title": "World Population",
            "topic": "population",
            "download_url": "https://example.com/pop.csv",
            "row_count": 1000,
            "summary": "Country populations",
        }
    )
    assert updated.title == "World Population"
    assert updated.row_count == 1000

    used = increment_usage(meta.dataset_id)
    assert used.usage_count == 1
    assert used.last_used is not None

    again = update_last_used(meta.dataset_id)
    assert again.last_used is not None

    delete_dataset(meta.dataset_id)


def test_validation_and_not_found():
    try:
        insert_dataset({"title": "No location"})
        assert False, "expected DatasetValidationError"
    except DatasetValidationError:
        pass

    try:
        update_dataset({"dataset_id": "missing-id-xyz", "title": "x", "topic": "y", "download_url": "http://x"})
        assert False, "expected DatasetNotFoundError"
    except DatasetNotFoundError:
        pass

    assert delete_dataset("missing-id-xyz") is False
