"""Dataset Registry — passive metadata store only.

Does not perform retrieval decisions, analysis, or DataFrame storage.
Storage backend is swappable via DatasetRegistryRepository.
"""

from backend.registry.exceptions import (
    DatasetNotFoundError,
    DatasetValidationError,
    RegistryError,
)
from backend.registry.models import DatasetMetadata, new_dataset_id
from backend.registry.repository import (
    DatasetRegistryRepository,
    SqlAlchemyDatasetRegistryRepository,
    ensure_registry_schema,
)
from backend.registry.service import (
    DatasetRegistryService,
    delete_dataset,
    get_by_dataset_id,
    get_by_topic,
    get_default_repository,
    increment_usage,
    insert_dataset,
    list_datasets,
    set_default_repository,
    update_dataset,
    update_last_used,
)

# Ensure table exists on import (same pattern as session / learned memory).
ensure_registry_schema()

__all__ = [
    "DatasetMetadata",
    "DatasetRegistryService",
    "DatasetRegistryRepository",
    "SqlAlchemyDatasetRegistryRepository",
    "RegistryError",
    "DatasetNotFoundError",
    "DatasetValidationError",
    "new_dataset_id",
    "ensure_registry_schema",
    "get_default_repository",
    "set_default_repository",
    "insert_dataset",
    "update_dataset",
    "get_by_topic",
    "get_by_dataset_id",
    "list_datasets",
    "increment_usage",
    "update_last_used",
    "delete_dataset",
]
