"""Dataset Library — physical file storage for downloaded datasets only.

Does not implement retrieval, registry cataloging, analysis, or LangGraph.
Cloud backends can replace LocalFilesystemStorage via set_default_storage().
"""

from backend.dataset_library.exceptions import (
    ChecksumMismatchError,
    DatasetFileNotFoundError,
    DatasetLibraryError,
    DatasetLibraryValidationError,
)
from backend.dataset_library.models import LibraryFileMetadata, SaveResult
from backend.dataset_library.service import (
    DatasetLibraryService,
    compute_checksum,
    dataset_exists,
    delete_dataset,
    get_dataset_path,
    get_default_storage,
    replace_dataset,
    save_dataset,
    set_default_storage,
    verify_checksum,
)
from backend.dataset_library.storage import DatasetStorage, LocalFilesystemStorage

__all__ = [
    "DatasetLibraryService",
    "DatasetStorage",
    "LocalFilesystemStorage",
    "LibraryFileMetadata",
    "SaveResult",
    "DatasetLibraryError",
    "DatasetFileNotFoundError",
    "DatasetLibraryValidationError",
    "ChecksumMismatchError",
    "save_dataset",
    "dataset_exists",
    "get_dataset_path",
    "delete_dataset",
    "replace_dataset",
    "compute_checksum",
    "verify_checksum",
    "get_default_storage",
    "set_default_storage",
]
