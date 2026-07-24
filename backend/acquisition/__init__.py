"""Dataset Acquisition — download, validate, and store via Dataset Library only."""

from backend.acquisition.exceptions import (
    AcquisitionError,
    AcquisitionValidationError,
    CorruptionError,
    DownloadError,
)
from backend.acquisition.models import AcquisitionResult
from backend.acquisition.service import DatasetAcquisitionService, acquire_dataset

__all__ = [
    "DatasetAcquisitionService",
    "AcquisitionResult",
    "acquire_dataset",
    "AcquisitionError",
    "AcquisitionValidationError",
    "DownloadError",
    "CorruptionError",
]
