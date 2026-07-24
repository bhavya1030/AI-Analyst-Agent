"""Unit tests for Dataset Library (file storage only)."""

import tempfile
from pathlib import Path

import pytest

from backend.dataset_library import (
    ChecksumMismatchError,
    DatasetLibraryValidationError,
    LocalFilesystemStorage,
    DatasetLibraryService,
    compute_checksum,
    dataset_exists,
    delete_dataset,
    get_dataset_path,
    replace_dataset,
    save_dataset,
    set_default_storage,
    verify_checksum,
)


@pytest.fixture()
def library_service(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "datasets")
    set_default_storage(storage)
    yield DatasetLibraryService(storage)
    # reset default to avoid leaking into other tests
    set_default_storage(LocalFilesystemStorage(tmp_path / "datasets_reset"))


def test_save_exists_path_checksum(library_service, tmp_path):
    content = b"year,value\n2020,1\n2021,2\n"
    result = library_service.save_dataset(
        dataset_id="ds-gold-1",
        data=content,
        source="World Bank",
        topic="India GDP",
        file_format="csv",
        version="1",
    )

    assert result.local_path
    assert Path(result.local_path).is_file()
    assert "world_bank" in result.relative_dir
    assert "india_gdp" in result.relative_dir
    assert result.checksum == compute_checksum(content)
    assert library_service.dataset_exists("ds-gold-1")
    assert library_service.get_dataset_path("ds-gold-1") == result.local_path
    assert verify_checksum("ds-gold-1") is True

    meta_path = Path(result.metadata_path)
    assert meta_path.is_file()
    text = meta_path.read_text(encoding="utf-8")
    assert "ds-gold-1" in text
    assert "checksum" in text


def test_replace_and_delete(library_service):
    v1 = library_service.save_dataset(
        dataset_id="ds-pop",
        data=b'{"a":1}\n',
        source="GitHub",
        topic="population",
        file_format="json",
    )
    v2 = library_service.replace_dataset(
        dataset_id="ds-pop",
        data=b'{"a":2}\n',
        source="GitHub",
        topic="population",
        file_format="json",
    )
    assert v2.replaced is True
    assert v2.version == "2"
    assert v2.checksum != v1.checksum
    assert verify_checksum("ds-pop") is True

    assert library_service.delete_dataset("ds-pop") is True
    assert library_service.dataset_exists("ds-pop") is False
    assert library_service.delete_dataset("ds-pop") is False


def test_checksum_mismatch(library_service):
    library_service.save_dataset(
        dataset_id="ds-x",
        data=b"a,b\n1,2\n",
        source="test",
        topic="t",
        file_format="csv",
    )
    with pytest.raises(ChecksumMismatchError):
        library_service.verify_checksum("ds-x", expected="0" * 64)


def test_unsupported_format(library_service):
    with pytest.raises(DatasetLibraryValidationError):
        library_service.save_dataset(
            dataset_id="ds-bad",
            data=b"x",
            source="s",
            topic="t",
            file_format="pdf",
        )


def test_module_level_api(tmp_path):
    set_default_storage(LocalFilesystemStorage(tmp_path / "lib"))
    save_dataset(
        dataset_id="mod-1",
        data=b"c1,c2\n",
        source="src",
        topic="topic",
        file_format="csv",
    )
    assert dataset_exists("mod-1")
    assert get_dataset_path("mod-1")
    replace_dataset(
        dataset_id="mod-1",
        data=b"c1,c2\n3,4\n",
        source="src",
        topic="topic",
        file_format="csv",
    )
    assert delete_dataset("mod-1") is True
