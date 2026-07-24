"""Registry-specific errors."""


class RegistryError(Exception):
    """Base error for dataset registry operations."""


class DatasetNotFoundError(RegistryError):
    """Raised when a dataset_id does not exist in the registry."""

    def __init__(self, dataset_id: str):
        self.dataset_id = dataset_id
        super().__init__(f"Dataset not found: {dataset_id}")


class DatasetValidationError(RegistryError):
    """Raised when metadata is incomplete or invalid."""
