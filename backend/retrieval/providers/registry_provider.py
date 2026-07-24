"""Dataset Registry provider — read metadata only; verify files via Library."""

from __future__ import annotations

from typing import Callable, Optional

from backend.core.logger import get_logger
from backend.retrieval.models import DatasetRequest, ProviderHit, RetrievalStatus
from backend.retrieval.providers.base import RetrievalProvider

logger = get_logger(__name__)


class RegistryProvider(RetrievalProvider):
    """
    Priority step 2: Dataset Registry (passive metadata) + Dataset Library check.

    - Registry hit + local file exists → REGISTRY_HIT
    - Registry hit + file missing (and no usable download_url only?) → STALE if local_path
      expected but missing; if only download_url, still REGISTRY_HIT with URL for engineer.

    Spec: "Verify the physical dataset exists using Dataset Library.
    If yes: REGISTRY_HIT. If registry entry exists but file is missing: STALE_REGISTRY_ENTRY.
    Do NOT automatically search."
    """

    name = "registry"

    def __init__(
        self,
        get_by_topic: Callable[..., list] | None = None,
        get_by_dataset_id: Callable[..., object] | None = None,
        dataset_exists: Callable[[str], bool] | None = None,
        get_dataset_path: Callable[[str], Optional[str]] | None = None,
    ):
        self._get_by_topic = get_by_topic
        self._get_by_dataset_id = get_by_dataset_id
        self._dataset_exists = dataset_exists
        self._get_dataset_path = get_dataset_path

    def try_retrieve(self, request: DatasetRequest) -> Optional[ProviderHit]:
        topic = request.normalized_topic()
        if not topic:
            return None

        records = self._lookup(topic)
        if not records:
            return None

        # Prefer highest usage / first match
        for record in records:
            hit = self._evaluate_record(record, topic)
            if hit is not None:
                return hit
        return None

    def _lookup(self, topic: str) -> list:
        if self._get_by_topic is None:
            return []
        try:
            results = self._get_by_topic(topic, limit=10)
            return list(results or [])
        except TypeError:
            try:
                return list(self._get_by_topic(topic) or [])
            except Exception as exc:
                logger.warning("RegistryProvider topic lookup failed", extra={"error": str(exc)})
                return []
        except Exception as exc:
            logger.warning("RegistryProvider topic lookup failed", extra={"error": str(exc)})
            return []

    def _evaluate_record(self, record, topic: str) -> Optional[ProviderHit]:
        meta = _record_to_dict(record)
        dataset_id = meta.get("dataset_id")
        local_path = meta.get("local_path")
        download_url = meta.get("download_url")

        file_ok = False
        resolved_path = None

        if dataset_id and self._dataset_exists is not None:
            try:
                file_ok = bool(self._dataset_exists(dataset_id))
            except Exception:
                file_ok = False
            if file_ok and self._get_dataset_path is not None:
                try:
                    resolved_path = self._get_dataset_path(dataset_id)
                except Exception:
                    resolved_path = local_path
        elif local_path:
            # Fallback: path string present but library not wired — treat as hint only
            from pathlib import Path

            file_ok = Path(local_path).is_file()
            resolved_path = local_path if file_ok else None

        if file_ok:
            logger.info(
                "RegistryProvider hit with local file",
                extra={"dataset_id": dataset_id, "topic": topic},
            )
            return ProviderHit(
                status=RetrievalStatus.REGISTRY_HIT,
                dataset_id=dataset_id,
                local_path=resolved_path or local_path,
                download_url=download_url,
                metadata=meta,
                reason=f"Registry match for topic '{topic}' with local library file.",
                provider_name=self.name,
            )

        # Registry knows the dataset but physical file is missing
        if dataset_id or local_path or download_url:
            # If we only have a remote URL and no library entry was ever saved,
            # still report STALE when local_path was claimed, else SEARCH if only URL?
            # Spec: file missing → STALE_REGISTRY_ENTRY (do not search here).
            if local_path or dataset_id:
                logger.info(
                    "RegistryProvider stale entry",
                    extra={"dataset_id": dataset_id, "topic": topic},
                )
                return ProviderHit(
                    status=RetrievalStatus.STALE_REGISTRY_ENTRY,
                    dataset_id=dataset_id,
                    local_path=local_path,
                    download_url=download_url,
                    metadata=meta,
                    reason=(
                        f"Registry has metadata for '{topic}' but local library file is missing."
                    ),
                    provider_name=self.name,
                )

            # Metadata with download_url only (never downloaded to library) → still a registry hit
            # for "known resource"; engineer may download later. Treat as REGISTRY_HIT with URL.
            if download_url:
                return ProviderHit(
                    status=RetrievalStatus.REGISTRY_HIT,
                    dataset_id=dataset_id,
                    local_path=None,
                    download_url=download_url,
                    metadata=meta,
                    reason=f"Registry match for topic '{topic}' with download_url only.",
                    provider_name=self.name,
                )

        return None


def _record_to_dict(record) -> dict:
    if record is None:
        return {}
    if isinstance(record, dict):
        return dict(record)
    if hasattr(record, "to_dict"):
        return record.to_dict()
    # SQLAlchemy-ish / simple namespace
    keys = (
        "dataset_id",
        "title",
        "topic",
        "description",
        "source",
        "source_type",
        "download_url",
        "local_path",
        "file_format",
        "tags",
        "columns",
        "row_count",
        "date_range",
        "summary",
        "usage_count",
        "checksum",
        "embedding_ref",
    )
    return {k: getattr(record, k, None) for k in keys}
