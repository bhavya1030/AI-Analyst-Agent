"""Abstract storage backend for the Dataset Library.

Local filesystem is the default. S3/Azure/GCS can implement the same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO, Optional, Union

from backend.dataset_library.models import LibraryFileMetadata

BytesLike = Union[bytes, bytearray, memoryview]
SourceData = Union[BytesLike, str, BinaryIO]  # bytes | path | file object


class DatasetStorage(ABC):
    """Physical object store for dataset files + sidecar metadata."""

    @abstractmethod
    def save(
        self,
        *,
        dataset_id: str,
        data: SourceData,
        relative_dir: str,
        data_filename: str,
        metadata: LibraryFileMetadata,
    ) -> str:
        """Persist data + metadata. Returns absolute/local path to the data file."""
        ...

    @abstractmethod
    def exists(self, dataset_id: str) -> bool:
        ...

    @abstractmethod
    def get_path(self, dataset_id: str) -> Optional[str]:
        """Return path/URI to the data file, or None if missing."""
        ...

    @abstractmethod
    def get_metadata(self, dataset_id: str) -> Optional[LibraryFileMetadata]:
        ...

    @abstractmethod
    def delete(self, dataset_id: str) -> bool:
        """Remove dataset directory. True if something was deleted."""
        ...

    @abstractmethod
    def replace(
        self,
        *,
        dataset_id: str,
        data: SourceData,
        relative_dir: str,
        data_filename: str,
        metadata: LibraryFileMetadata,
    ) -> str:
        """Overwrite existing dataset payload (or create if absent). Returns data path."""
        ...

    @abstractmethod
    def read_bytes(self, dataset_id: str) -> bytes:
        """Read full data file bytes (for checksum verification)."""
        ...
