"""Storage backends for Dataset Library."""

from backend.dataset_library.storage.base import DatasetStorage
from backend.dataset_library.storage.local import LocalFilesystemStorage

__all__ = ["DatasetStorage", "LocalFilesystemStorage"]
