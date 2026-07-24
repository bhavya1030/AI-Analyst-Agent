"""Dataset Acquisition Service — download + validate + save to Dataset Library.

Does NOT clean data, build DataFrames, run EDA, or talk to Planner/LangGraph.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Optional, Sequence

from backend.acquisition.detection import (
    detect_format,
    extract_supported_from_zip,
    validate_content,
)
from backend.acquisition.downloaders.base import DatasetDownloader, DownloadPayload
from backend.acquisition.downloaders.github_raw_downloader import GitHubRawDownloader
from backend.acquisition.downloaders.http_downloader import HttpDownloader
from backend.acquisition.downloaders.huggingface_downloader import HuggingFaceDownloader
from backend.acquisition.downloaders.world_bank_downloader import WorldBankDownloader
from backend.acquisition.exceptions import (
    AcquisitionValidationError,
    CorruptionError,
    DownloadError,
)
from backend.acquisition.models import AcquisitionResult, _utc_now_iso
from backend.core.logger import get_logger
from backend.dataset_library import DatasetLibraryService, get_default_storage
from backend.dataset_library.formats import is_supported_format

logger = get_logger(__name__)


def _default_downloaders(max_retries: int = 3) -> list[DatasetDownloader]:
    http = HttpDownloader(max_retries=max_retries)
    # Order: specialized first, generic HTTP last
    return [
        GitHubRawDownloader(http=http),
        HuggingFaceDownloader(http=http),
        WorldBankDownloader(http=http),
        http,
    ]


class DatasetAcquisitionService:
    """Acquire remote datasets and persist them via Dataset Library."""

    def __init__(
        self,
        *,
        library: DatasetLibraryService | None = None,
        downloaders: Sequence[DatasetDownloader] | None = None,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        self._library = library or DatasetLibraryService(get_default_storage())
        self._downloaders = list(downloaders) if downloaders is not None else _default_downloaders(max_retries)
        self.max_retries = max_retries
        self.timeout = timeout

    def acquire(self, retrieval_result: Any) -> AcquisitionResult:
        """
        Accept a RetrievalResult (object or dict) and acquire the dataset.

        Priority for location:
          1. local_path if file already exists
          2. download_url via modular downloaders
        """
        started = _utc_now_iso()
        try:
            payload = self._normalize_retrieval(retrieval_result)
        except AcquisitionValidationError as exc:
            return AcquisitionResult.failure(str(exc), acquisition_time=started)

        dataset_id = payload.get("dataset_id") or str(uuid.uuid4())
        topic = payload.get("topic") or (payload.get("metadata") or {}).get("topic") or "dataset"
        source = (
            payload.get("provider")
            or (payload.get("metadata") or {}).get("source")
            or "unknown"
        )
        local_path = payload.get("local_path")
        download_url = payload.get("download_url")
        metadata = payload.get("metadata") or {}

        # 1) Already local
        if local_path and Path(local_path).is_file():
            try:
                raw = Path(local_path).read_bytes()
                checksum = hashlib.sha256(raw).hexdigest()
                detected = detect_format(raw, url=local_path, metadata=metadata)
                errors = validate_content(raw, detected)
                if errors:
                    return AcquisitionResult.failure(
                        *errors,
                        acquisition_time=started,
                        dataset_id=dataset_id,
                        source_url=download_url,
                        provider=payload.get("provider"),
                        local_path=local_path,
                        detected_format=detected,
                        dataset_size=len(raw),
                        checksum=checksum,
                    )
                return AcquisitionResult(
                    success=True,
                    local_path=str(Path(local_path).resolve()),
                    checksum=checksum,
                    detected_format=detected,
                    dataset_size=len(raw),
                    acquisition_time=started,
                    errors=[],
                    dataset_id=dataset_id,
                    source_url=download_url,
                    provider=payload.get("provider"),
                    reused_existing=True,
                )
            except Exception as exc:
                return AcquisitionResult.failure(
                    f"Failed to read local_path: {exc}",
                    acquisition_time=started,
                    dataset_id=dataset_id,
                )

        if not download_url:
            return AcquisitionResult.failure(
                "RetrievalResult has no download_url or usable local_path.",
                acquisition_time=started,
                dataset_id=dataset_id,
                provider=payload.get("provider"),
            )

        # 2) Download
        try:
            downloaded = self._download(download_url)
        except Exception as exc:
            return AcquisitionResult.failure(
                f"Download failed: {exc}",
                acquisition_time=started,
                dataset_id=dataset_id,
                source_url=download_url,
                provider=payload.get("provider"),
            )

        content = downloaded.content
        final_url = downloaded.final_url or download_url

        # 3) Detect + validate (handle ZIP)
        detected = detect_format(content, url=final_url, metadata=metadata)
        member_name = None

        if detected == "zip":
            try:
                content, detected, member_name = extract_supported_from_zip(content)
            except Exception as exc:
                return AcquisitionResult.failure(
                    f"ZIP extraction failed: {exc}",
                    acquisition_time=started,
                    dataset_id=dataset_id,
                    source_url=final_url,
                    provider=payload.get("provider"),
                    detected_format="zip",
                )

        errors = validate_content(content, detected)
        if errors:
            return AcquisitionResult.failure(
                *errors,
                acquisition_time=started,
                dataset_id=dataset_id,
                source_url=final_url,
                provider=payload.get("provider"),
                detected_format=detected,
                dataset_size=len(content),
            )

        if not is_supported_format(detected) and detected not in {"csv", "json", "xlsx", "xls", "parquet"}:
            return AcquisitionResult.failure(
                f"Unsupported format after download: {detected}",
                acquisition_time=started,
                dataset_id=dataset_id,
                source_url=final_url,
                detected_format=detected,
                dataset_size=len(content),
            )

        # 4) Checksum
        checksum = hashlib.sha256(content).hexdigest()

        # 5) Save via Dataset Library
        try:
            save_kwargs = dict(
                dataset_id=dataset_id,
                data=content,
                source=str(source),
                topic=str(topic),
                file_format=detected,
                version="1",
                checksum=checksum,
            )
            if self._library.dataset_exists(dataset_id):
                save_result = self._library.replace_dataset(**save_kwargs)
            else:
                save_result = self._library.save_dataset(**save_kwargs)
        except Exception as exc:
            return AcquisitionResult.failure(
                f"Failed to save into Dataset Library: {exc}",
                acquisition_time=started,
                dataset_id=dataset_id,
                source_url=final_url,
                provider=payload.get("provider"),
                detected_format=detected,
                dataset_size=len(content),
                checksum=checksum,
            )

        # 6) Optional post-save integrity check against library
        try:
            self._library.verify_checksum(dataset_id, expected=checksum)
        except Exception as exc:
            return AcquisitionResult.failure(
                f"Post-save checksum verification failed: {exc}",
                acquisition_time=started,
                dataset_id=dataset_id,
                local_path=save_result.local_path,
                source_url=final_url,
                checksum=checksum,
                detected_format=detected,
                dataset_size=len(content),
            )

        logger.info(
            "Dataset acquired",
            extra={
                "dataset_id": dataset_id,
                "format": detected,
                "size": len(content),
                "path": save_result.local_path,
                "member": member_name,
            },
        )

        return AcquisitionResult(
            success=True,
            local_path=save_result.local_path,
            checksum=checksum,
            detected_format=detected,
            dataset_size=len(content),
            acquisition_time=started,
            errors=[],
            dataset_id=dataset_id,
            source_url=final_url,
            provider=payload.get("provider"),
            reused_existing=False,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _download(self, url: str) -> DownloadPayload:
        downloader = self._select_downloader(url)
        # Specialized downloaders may use nested HttpDownloader retries;
        # still wrap once for clear errors.
        try:
            return downloader.download(url, timeout=self.timeout)
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(str(exc)) from exc

    def _select_downloader(self, url: str) -> DatasetDownloader:
        for downloader in self._downloaders:
            try:
                if downloader.can_handle(url):
                    return downloader
            except Exception:
                continue
        # Fallback absolute last: first HTTP downloader if present
        for downloader in self._downloaders:
            if isinstance(downloader, HttpDownloader):
                return downloader
        raise DownloadError(f"No downloader available for URL: {url}")

    def _normalize_retrieval(self, retrieval_result: Any) -> dict[str, Any]:
        if retrieval_result is None:
            raise AcquisitionValidationError("retrieval_result is required")

        if hasattr(retrieval_result, "to_dict"):
            data = retrieval_result.to_dict()
        elif isinstance(retrieval_result, dict):
            data = dict(retrieval_result)
        else:
            # duck-type RetrievalResult fields
            data = {
                "status": getattr(retrieval_result, "status", None),
                "dataset_id": getattr(retrieval_result, "dataset_id", None),
                "local_path": getattr(retrieval_result, "local_path", None),
                "download_url": getattr(retrieval_result, "download_url", None),
                "metadata": getattr(retrieval_result, "metadata", None),
                "provider": getattr(retrieval_result, "provider", None),
                "topic": getattr(retrieval_result, "topic", None),
                "reason": getattr(retrieval_result, "reason", None),
            }

        # status may be enum
        status = data.get("status")
        status_val = status.value if hasattr(status, "value") else status
        if status_val in {"SEARCH_REQUIRED", "NOT_FOUND"}:
            raise AcquisitionValidationError(
                f"Cannot acquire dataset for status={status_val}: {data.get('reason') or ''}"
            )

        if not data.get("download_url") and not data.get("local_path"):
            # metadata may carry url
            meta = data.get("metadata") or {}
            data["download_url"] = data.get("download_url") or meta.get("download_url") or meta.get("url")
            data["local_path"] = data.get("local_path") or meta.get("local_path")

        if not data.get("download_url") and not data.get("local_path"):
            raise AcquisitionValidationError(
                "RetrievalResult missing download_url and local_path"
            )

        if not data.get("topic"):
            meta = data.get("metadata") or {}
            data["topic"] = meta.get("topic") or meta.get("title") or "dataset"

        return data


# Module-level convenience


def acquire_dataset(
    retrieval_result: Any,
    *,
    max_retries: int = 3,
    timeout: int = 60,
) -> AcquisitionResult:
    return DatasetAcquisitionService(max_retries=max_retries, timeout=timeout).acquire(
        retrieval_result
    )
