"""Errors for the Dataset Library (file storage only)."""


class DatasetLibraryError(Exception):
    """Base library error."""


class DatasetFileNotFoundError(DatasetLibraryError):
    def __init__(self, dataset_id: str):
        self.dataset_id = dataset_id
        super().__init__(f"Dataset file not found in library: {dataset_id}")


class DatasetLibraryValidationError(DatasetLibraryError):
    """Invalid arguments or unsupported format."""


class ChecksumMismatchError(DatasetLibraryError):
    def __init__(self, dataset_id: str, expected: str, actual: str):
        self.dataset_id = dataset_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Checksum mismatch for {dataset_id}: expected {expected}, got {actual}"
        )
