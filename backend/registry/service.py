"""Service layer for Dataset Registry.

Public API used by future Retrieval Agent / Data Engineer.
Contains no discovery policy and never stores DataFrames or analysis.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.core.logger import get_logger
from backend.registry.exceptions import DatasetNotFoundError, DatasetValidationError
from backend.registry.models import DatasetMetadata, _utc_now_iso, new_dataset_id
from backend.registry.repository import (
    DatasetRegistryRepository,
    SqlAlchemyDatasetRegistryRepository,
    ensure_registry_schema,
)

logger = get_logger(__name__)

# Module-level default repository (swap for Postgres/Mongo implementations later).
_default_repository: DatasetRegistryRepository | None = None


def get_default_repository() -> DatasetRegistryRepository:
    global _default_repository
    if _default_repository is None:
        ensure_registry_schema()
        _default_repository = SqlAlchemyDatasetRegistryRepository()
    return _default_repository


def set_default_repository(repository: DatasetRegistryRepository) -> None:
    """Inject alternate storage backend (tests, Postgres, Mongo adapter)."""
    global _default_repository
    _default_repository = repository


class DatasetRegistryService:
    """High-level registry operations — metadata store only."""

    def __init__(self, repository: DatasetRegistryRepository | None = None):
        self._repo = repository or get_default_repository()

    # ------------------------------------------------------------------
    # Public API required by Task 3
    # ------------------------------------------------------------------

    def insert_dataset(self, metadata: dict[str, Any] | DatasetMetadata) -> DatasetMetadata:
        meta = self._coerce_metadata(metadata, require_identity=False)
        if not meta.title and not meta.topic:
            raise DatasetValidationError("title or topic is required")
        if not meta.download_url and not meta.local_path:
            raise DatasetValidationError("download_url or local_path is required")

        if not meta.dataset_id:
            meta.dataset_id = new_dataset_id()
        now = _utc_now_iso()
        meta.created_at = meta.created_at or now
        meta.last_updated = now
        if meta.usage_count is None:
            meta.usage_count = 0

        saved = self._repo.insert(meta)
        logger.info(
            "Registry insert",
            extra={"dataset_id": saved.dataset_id, "topic": saved.topic},
        )
        return saved

    def update_dataset(self, metadata: dict[str, Any] | DatasetMetadata) -> DatasetMetadata:
        meta = self._coerce_metadata(metadata, require_identity=True)
        existing = self._repo.get_by_dataset_id(meta.dataset_id)
        if existing is None:
            raise DatasetNotFoundError(meta.dataset_id)

        # Preserve immutable-ish fields if caller omitted them
        merged = existing.to_dict()
        incoming = meta.to_dict()
        for key, value in incoming.items():
            if key == "dataset_id":
                continue
            if value is None and key in {
                "download_url",
                "local_path",
                "row_count",
                "date_range",
                "checksum",
                "embedding_ref",
                "last_used",
            }:
                # allow explicit nulls for optional fields only when provided as key
                if isinstance(metadata, dict) and key in metadata:
                    merged[key] = value
                continue
            if isinstance(metadata, dict) and key not in metadata and key not in (
                "last_updated",
            ):
                # dataclass path always has keys; dict path partial update
                if not isinstance(metadata, DatasetMetadata):
                    continue
            merged[key] = value

        # For DatasetMetadata objects, prefer full replace of provided model
        if isinstance(metadata, DatasetMetadata):
            merged = meta.to_dict()
            merged["created_at"] = existing.created_at
            merged["usage_count"] = (
                meta.usage_count if meta.usage_count is not None else existing.usage_count
            )

        merged["dataset_id"] = existing.dataset_id
        merged["created_at"] = existing.created_at
        merged["last_updated"] = _utc_now_iso()
        updated = DatasetMetadata.from_dict(merged)
        saved = self._repo.update(updated)
        logger.info(
            "Registry update",
            extra={"dataset_id": saved.dataset_id, "topic": saved.topic},
        )
        return saved

    def get_by_topic(self, topic: str, *, limit: int = 20) -> list[DatasetMetadata]:
        """Raw candidate recall (may include weak partials). Prefer match_topic()."""
        return self._repo.get_by_topic(topic, limit=limit)

    def match_topic(
        self,
        topic: str,
        *,
        question: str | None = None,
        intent: str | None = None,
        limit: int = 5,
        min_confidence: float | None = None,
        semantic_scores: dict[str, float] | None = None,
    ) -> list:
        """
        High-confidence registry matches with explanations.

        Returns list[MatchScore] (accepted only). Empty → caller should
        perform internet / open-data retrieval instead of REGISTRY_HIT.
        """
        from backend.registry.matching import DEFAULT_MIN_CONFIDENCE, match_registry

        candidates = self._repo.get_by_topic(topic, limit=max(limit * 5, 20))
        # Also consider a broader active list when candidate recall is empty
        if not candidates:
            candidates = self._repo.list_all(limit=50, active_only=True)
        return match_registry(
            topic,
            candidates,
            question=question,
            intent=intent,
            semantic_scores=semantic_scores,
            min_confidence=(
                min_confidence
                if min_confidence is not None
                else DEFAULT_MIN_CONFIDENCE
            ),
            limit=limit,
        )

    def get_by_dataset_id(self, dataset_id: str) -> Optional[DatasetMetadata]:
        if not dataset_id:
            return None
        return self._repo.get_by_dataset_id(dataset_id)

    def list_datasets(self, *, limit: int = 100, active_only: bool = True) -> list[DatasetMetadata]:
        return self._repo.list_all(limit=limit, active_only=active_only)

    def increment_usage(self, dataset_id: str) -> DatasetMetadata:
        if not dataset_id:
            raise DatasetValidationError("dataset_id is required")
        updated = self._repo.increment_usage(dataset_id)
        # Also refresh last_used for convenience when usage is recorded
        return self._repo.update_last_used(dataset_id, _utc_now_iso())

    def update_last_used(self, dataset_id: str, timestamp: str | None = None) -> DatasetMetadata:
        if not dataset_id:
            raise DatasetValidationError("dataset_id is required")
        ts = timestamp or _utc_now_iso()
        return self._repo.update_last_used(dataset_id, ts)

    def delete_dataset(self, dataset_id: str) -> bool:
        if not dataset_id:
            return False
        deleted = self._repo.delete(dataset_id)
        if deleted:
            logger.info("Registry delete", extra={"dataset_id": dataset_id})
        return deleted

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _coerce_metadata(
        self,
        metadata: dict[str, Any] | DatasetMetadata,
        *,
        require_identity: bool,
    ) -> DatasetMetadata:
        if isinstance(metadata, DatasetMetadata):
            meta = metadata
        elif isinstance(metadata, dict):
            meta = DatasetMetadata.from_dict(metadata)
        else:
            raise DatasetValidationError("metadata must be a dict or DatasetMetadata")

        if require_identity and not meta.dataset_id:
            raise DatasetValidationError("dataset_id is required for update")
        return meta


# Module-level convenience functions matching the required API names.


def insert_dataset(metadata: dict[str, Any] | DatasetMetadata) -> DatasetMetadata:
    return DatasetRegistryService().insert_dataset(metadata)


def update_dataset(metadata: dict[str, Any] | DatasetMetadata) -> DatasetMetadata:
    return DatasetRegistryService().update_dataset(metadata)


def get_by_topic(topic: str, *, limit: int = 20) -> list[DatasetMetadata]:
    return DatasetRegistryService().get_by_topic(topic, limit=limit)


def match_topic(
    topic: str,
    *,
    question: str | None = None,
    intent: str | None = None,
    limit: int = 5,
    min_confidence: float | None = None,
    semantic_scores: dict[str, float] | None = None,
) -> list:
    return DatasetRegistryService().match_topic(
        topic,
        question=question,
        intent=intent,
        limit=limit,
        min_confidence=min_confidence,
        semantic_scores=semantic_scores,
    )


def get_by_dataset_id(dataset_id: str) -> Optional[DatasetMetadata]:
    return DatasetRegistryService().get_by_dataset_id(dataset_id)


def list_datasets(*, limit: int = 100, active_only: bool = True) -> list[DatasetMetadata]:
    return DatasetRegistryService().list_datasets(limit=limit, active_only=active_only)


def increment_usage(dataset_id: str) -> DatasetMetadata:
    return DatasetRegistryService().increment_usage(dataset_id)


def update_last_used(dataset_id: str, timestamp: str | None = None) -> DatasetMetadata:
    return DatasetRegistryService().update_last_used(dataset_id, timestamp)


def delete_dataset(dataset_id: str) -> bool:
    return DatasetRegistryService().delete_dataset(dataset_id)
