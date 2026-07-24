"""Tests for Dataset Acquisition Service."""

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.acquisition import AcquisitionResult, DatasetAcquisitionService, acquire_dataset
from backend.acquisition.downloaders.base import DownloadPayload
from backend.acquisition.downloaders.github_raw_downloader import GitHubRawDownloader
from backend.acquisition.downloaders.http_downloader import HttpDownloader
from backend.dataset_library import LocalFilesystemStorage, set_default_storage
from backend.dataset_library.service import DatasetLibraryService
from backend.retrieval.models import NextAction, RetrievalResult, RetrievalStatus


@pytest.fixture()
def acq_service(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "datasets")
    set_default_storage(storage)
    library = DatasetLibraryService(storage)
    # Avoid real network: inject a fake HTTP downloader
    fake = _FakeHttpDownloader(
        {
            "https://example.com/data.csv": b"a,b\n1,2\n3,4\n",
            "https://raw.githubusercontent.com/org/repo/main/data.csv": b"x,y\n9,8\n",
            "https://example.com/blob.zip": _make_zip_csv(),
        }
    )
    service = DatasetAcquisitionService(
        library=library,
        downloaders=[
            GitHubRawDownloader(http=fake),
            fake,
        ],
        max_retries=2,
        timeout=5,
    )
    return service


def _make_zip_csv() -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("inner/data.csv", "col1,col2\n10,20\n")
    return buf.getvalue()


class _FakeHttpDownloader(HttpDownloader):
    name = "http"

    def __init__(self, mapping: dict[str, bytes]):
        super().__init__(max_retries=1)
        self.mapping = mapping

    def can_handle(self, url: str) -> bool:
        return url.startswith("http")

    def download(self, url: str, *, timeout: int = 60) -> DownloadPayload:
        # GitHub normalizer may rewrite URL — match prefix or exact
        if url in self.mapping:
            content = self.mapping[url]
        else:
            # try raw rewrite already applied
            for key, val in self.mapping.items():
                if key in url or url in key:
                    content = val
                    break
            else:
                from backend.acquisition.exceptions import DownloadError

                raise DownloadError(f"no fake mapping for {url}")
        return DownloadPayload(content=content, final_url=url, content_type="text/csv")


def test_acquire_csv_from_retrieval_result(acq_service):
    retrieval = RetrievalResult(
        status=RetrievalStatus.INTERNET_HIT,
        download_url="https://example.com/data.csv",
        provider="internet_search:GitHub",
        topic="demo",
        metadata={"source": "test", "file_format": "csv"},
        next_action=NextAction.USE_DOWNLOAD_URL,
    )
    result = acq_service.acquire(retrieval)
    assert result.success is True
    assert result.local_path and Path(result.local_path).is_file()
    assert result.detected_format == "csv"
    assert result.checksum
    assert result.dataset_size and result.dataset_size > 0
    assert result.errors == []


def test_acquire_zip_extracts_csv(acq_service):
    retrieval = {
        "status": "INTERNET_HIT",
        "download_url": "https://example.com/blob.zip",
        "topic": "zipped",
        "provider": "http",
        "metadata": {},
    }
    result = acq_service.acquire(retrieval)
    assert result.success is True
    assert result.detected_format == "csv"
    assert Path(result.local_path).read_text(encoding="utf-8").startswith("col1")


def test_github_raw_normalization():
    d = GitHubRawDownloader(http=_FakeHttpDownloader({
        "https://raw.githubusercontent.com/org/repo/main/data.csv": b"a,b\n1,2\n",
    }))
    assert d.can_handle("https://github.com/org/repo/blob/main/data.csv")
    payload = d.download("https://github.com/org/repo/blob/main/data.csv")
    assert b"a,b" in payload.content


def test_reuse_local_path(acq_service, tmp_path):
    f = tmp_path / "already.csv"
    f.write_text("h1,h2\n5,6\n", encoding="utf-8")
    result = acq_service.acquire(
        {
            "status": "REGISTRY_HIT",
            "local_path": str(f),
            "topic": "local",
            "dataset_id": "local-1",
        }
    )
    assert result.success is True
    assert result.reused_existing is True
    assert result.detected_format == "csv"


def test_missing_url_fails(acq_service):
    result = acq_service.acquire(
        {"status": "SEARCH_REQUIRED", "topic": "x", "reason": "none"}
    )
    assert result.success is False
    assert result.errors


def test_module_level_api(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "lib")
    set_default_storage(storage)
    # patch default service downloaders by calling acquire_dataset with a local path only
    f = tmp_path / "m.csv"
    f.write_bytes(b"a,b\n1,2\n")
    result = acquire_dataset(
        {
            "status": "SESSION_HIT",
            "local_path": str(f),
            "topic": "t",
            "dataset_id": "id-mod",
        }
    )
    assert isinstance(result, AcquisitionResult)
    assert result.success is True
