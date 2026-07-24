"""Errors for Dataset Acquisition Service."""


class AcquisitionError(Exception):
    """Base acquisition error."""


class AcquisitionValidationError(AcquisitionError):
    """Invalid RetrievalResult or unsupported resource."""


class DownloadError(AcquisitionError):
    """Download failed after retries or invalid response."""


class CorruptionError(AcquisitionError):
    """Downloaded content failed integrity / format validation."""
