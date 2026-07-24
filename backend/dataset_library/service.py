"""Service layer for the Dataset Library.

Manages physical dataset files only. No registry, agents, or analysis.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.core.logger import get_logger
from backend.dataset_library.exceptions import (
    ChecksumMismatchError,
    DatasetFileNotFoundError,
    DatasetLibraryValidationError,
)
from backend.dataset_library.formats import data_filename, is_supported_format, normalize_format
from backend.dataset_library.models import LibraryFileMetadata, SaveResult, _utc_now_iso
from backend.dataset_library.naming import dataset_relative_dir
from backend.dataset_library.storage.base import DatasetStorage, SourceData
from backend.dataset_library.storage.local import LocalFilesystemStorage

logger = get_logger(__name__)

_default_storage: DatasetStorage | None = None


def default_library_root() -> Path:
    """Root folder for on-disk datasets (under project data dir)."""
    return Path(settings.DATA_DIR) / "datasets"


def get_default_storage() -> DatasetStorage:
    global _default_storage
    if _default_storage is None:
        _default_storage = LocalFilesystemStorage(default_library_root())
    return _default_storage


def set_default_storage(storage: DatasetStorage) -> None:
    """Inject S3/Azure/GCS (or test) backend later without changing call sites."""
    global _default_storage
    _default_storage = storage


class DatasetLibraryService:
    """High-level file library operations."""

    def __init__(self, storage: DatasetStorage | None = None):
        self._storage = storage or get_default_storage()

    # ------------------------------------------------------------------
    # Required public API
    # ------------------------------------------------------------------

    def save_dataset(
        self,
        *,
        dataset_id: str,
        data: SourceData,
        source: str = "",
        topic: str = "",
        file_format: str = "csv",
        version: str = "1",
        checksum: str | None = None,
    ) -> SaveResult:
        """Save a new dataset into the library. Fails if dataset_id already exists."""
        dataset_id = (dataset_id or "").strip()
        if not dataset_id:
            raise DatasetLibraryValidationError("dataset_id is required")

        fmt = normalize_format(file_format)
        if not is_supported_format(fmt):
            raise DatasetLibraryValidationError(
                f"Unsupported file_format: {file_format}. "
                f"Supported: csv, json, xlsx, xls, parquet"
            )

        raw = _peek_bytes(data)
        digest = checksum or self.compute_checksum(raw)
        rel = dataset_relative_dir(source, topic, dataset_id)
        fname = data_filename(fmt)

        meta = LibraryFileMetadata(
            dataset_id=dataset_id,
            checksum=digest,
            download_time=_utc_now_iso(),
            source=source or "",
            file_format=fmt,
            version=str(version or "1"),
            relative_dir=rel,
            data_filename=fname,
            topic=topic or "",
        )

        path = self._storage.save(
            dataset_id=dataset_id,
            data=raw,
            relative_dir=rel,
            data_filename=fname,
            metadata=meta,
        )
        logger.info(
            "Dataset saved to library",
            extra={"dataset_id": dataset_id, "path": path, "checksum": digest},
        )
        return SaveResult(
            dataset_id=dataset_id,
            local_path=path,
            checksum=digest,
            file_format=fmt,
            relative_dir=rel,
            metadata_path=str(Path(path).parent / "metadata.json"),
            version=meta.version,
            replaced=False,
        )

    def dataset_exists(self, dataset_id: str) -> bool:
        if not dataset_id:
            return False
        return self._storage.exists(dataset_id)

    def get_dataset_path(self, dataset_id: str) -> Optional[str]:
        if not dataset_id:
            return None
        return self._storage.get_path(dataset_id)

    def delete_dataset(self, dataset_id: str) -> bool:
        if not dataset_id:
            return False
        deleted = self._storage.delete(dataset_id)
        if deleted:
            logger.info("Dataset deleted from library", extra={"dataset_id": dataset_id})
        return deleted

    def replace_dataset(
        self,
        *,
        dataset_id: str,
        data: SourceData,
        source: str = "",
        topic: str = "",
        file_format: str = "csv",
        version: str | None = None,
        checksum: str | None = None,
    ) -> SaveResult:
        """Replace an existing dataset (or create if missing). Bumps version when omitted."""
        dataset_id = (dataset_id or "").strip()
        if not dataset_id:
            raise DatasetLibraryValidationError("dataset_id is required")

        fmt = normalize_format(file_format)
        if not is_supported_format(fmt):
            raise DatasetLibraryValidationError(f"Unsupported file_format: {file_format}")

        existing = self._storage.get_metadata(dataset_id)
        if version is None:
            if existing and existing.version:
                try:
                    version = str(int(existing.version) + 1)
                except ValueError:
                    version = f"{existing.version}.1"
            else:
                version = "1"

        # Prefer previous source/topic for stable paths if not provided
        source = source or (existing.source if existing else "") or ""
        topic = topic or (existing.topic if existing else "") or ""

        raw = _peek_bytes(data)
        digest = checksum or self.compute_checksum(raw)
        rel = dataset_relative_dir(source, topic, dataset_id)
        fname = data_filename(fmt)

        meta = LibraryFileMetadata(
            dataset_id=dataset_id,
            checksum=digest,
            download_time=_utc_now_iso(),
            source=source,
            file_format=fmt,
            version=str(version),
            relative_dir=rel,
            data_filename=fname,
            topic=topic,
        )

        path = self._storage.replace(
            dataset_id=dataset_id,
            data=raw,
            relative_dir=rel,
            data_filename=fname,
            metadata=meta,
        )
        logger.info(
            "Dataset replaced in library",
            extra={"dataset_id": dataset_id, "version": version, "path": path},
        )
        return SaveResult(
            dataset_id=dataset_id,
            local_path=path,
            checksum=digest,
            file_format=fmt,
            relative_dir=rel,
            metadata_path=str(Path(path).parent / "metadata.json"),
            version=str(version),
            replaced=True,
        )

    def compute_checksum(self, data: SourceData | bytes) -> str:
        """SHA-256 hex digest of file contents."""
        raw = data if isinstance(data, (bytes, bytearray, memoryview)) else _peek_bytes(data)
        return hashlib.sha256(bytes(raw)).hexdigest()

    def verify_checksum(self, dataset_id: str, expected: str | None = None) -> bool:
        """Verify on-disk file against expected or sidecar checksum.

        Returns True if match. Raises ChecksumMismatchError on mismatch.
        Raises DatasetFileNotFoundError if missing.
        """
        meta = self._storage.get_metadata(dataset_id)
        if meta is None:
            raise DatasetFileNotFoundError(dataset_id)

        expected_digest = (expected or meta.checksum or "").strip().lower()
        if not expected_digest:
            raise DatasetLibraryValidationError(
                f"No checksum available to verify for {dataset_id}"
            )

        raw = self._storage.read_bytes(dataset_id)
        actual = self.compute_checksum(raw).lower()
        if actual != expected_digest:
            raise ChecksumMismatchError(dataset_id, expected_digest, actual)
        return True

    # Convenience
    def get_file_metadata(self, dataset_id: str) -> Optional[LibraryFileMetadata]:
        return self._storage.get_metadata(dataset_id)


def _peek_bytes(data: SourceData) -> bytes:
    """Materialize bytes once so checksum and write share the same content."""
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    if isinstance(data, str):
        path = Path(data)
        if not path.is_file():
            raise DatasetLibraryValidationError(f"Source path is not a file: {data}")
        return path.read_bytes()
    if hasattr(data, "read"):
        chunk = data.read()
        if isinstance(chunk, str):
            return chunk.encode("utf-8")
        return bytes(chunk)
    raise DatasetLibraryValidationError("Unsupported data source type")


# ---------------------------------------------------------------------------
# Module-level API (required names)
# ---------------------------------------------------------------------------


def save_dataset(**kwargs) -> SaveResult:
    return DatasetLibraryService().save_dataset(**kwargs)


def dataset_exists(dataset_id: str) -> bool:
    return DatasetLibraryService().dataset_exists(dataset_id)


def get_dataset_path(dataset_id: str) -> Optional[str]:
    return DatasetLibraryService().get_dataset_path(dataset_id)


def delete_dataset(dataset_id: str) -> bool:
    return DatasetLibraryService().delete_dataset(dataset_id)


def replace_dataset(**kwargs) -> SaveResult:
    return DatasetLibraryService().replace_dataset(**kwargs)


def compute_checksum(data: SourceData | bytes) -> str:
    return DatasetLibraryService().compute_checksum(data)


def verify_checksum(dataset_id: str, expected: str | None = None) -> bool:
    return DatasetLibraryService().verify_checksum(dataset_id, expected)
