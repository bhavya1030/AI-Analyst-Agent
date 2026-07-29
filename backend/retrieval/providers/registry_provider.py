"""Dataset Registry provider — high-confidence multi-signal matching only."""

from __future__ import annotations

from typing import Callable, Optional

from backend.core.logger import get_logger
from backend.registry.matching import DEFAULT_MIN_CONFIDENCE, MatchScore, match_registry
from backend.retrieval.models import DatasetRequest, ProviderHit, RetrievalStatus
from backend.retrieval.providers.base import RetrievalProvider

logger = get_logger(__name__)


class RegistryProvider(RetrievalProvider):
    """
    Priority step 2: Dataset Registry with confidence scoring.

    - Candidate recall via get_by_topic / list
    - Multi-signal score (topic, domain, keywords, columns, country, intent)
    - Reject if confidence < threshold → return None (internet retrieval next)
    - On accept: REGISTRY_HIT or STALE_REGISTRY_ENTRY with match explanation
    """

    name = "registry"

    def __init__(
        self,
        get_by_topic: Callable[..., list] | None = None,
        get_by_dataset_id: Callable[..., object] | None = None,
        dataset_exists: Callable[[str], bool] | None = None,
        get_dataset_path: Callable[[str], Optional[str]] | None = None,
        list_datasets: Callable[..., list] | None = None,
        match_topic: Callable[..., list] | None = None,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ):
        self._get_by_topic = get_by_topic
        self._get_by_dataset_id = get_by_dataset_id
        self._dataset_exists = dataset_exists
        self._get_dataset_path = get_dataset_path
        self._list_datasets = list_datasets
        self._match_topic = match_topic
        self.min_confidence = float(min_confidence)

    def try_retrieve(self, request: DatasetRequest) -> Optional[ProviderHit]:
        topic = request.normalized_topic()
        if not topic:
            return None

        match = self._best_match(request)
        if match is None or not match.accepted or not match.metadata:
            logger.info(
                "RegistryProvider: no high-confidence match",
                extra={
                    "topic": topic,
                    "threshold": self.min_confidence,
                    "reason": match.explanation if match else "no_candidates",
                },
            )
            return None

        return self._evaluate_record(match, topic)

    def _best_match(self, request: DatasetRequest) -> Optional[MatchScore]:
        topic = request.normalized_topic()
        # Prefer service-level match_topic when wired
        if self._match_topic is not None:
            try:
                hits = self._match_topic(
                    topic,
                    question=request.question,
                    limit=5,
                    min_confidence=self.min_confidence,
                )
                if hits:
                    return hits[0]
                return None
            except TypeError:
                try:
                    hits = self._match_topic(topic)
                    if hits and getattr(hits[0], "accepted", False):
                        return hits[0]
                except Exception as exc:
                    logger.warning("match_topic failed", extra={"error": str(exc)})
            except Exception as exc:
                logger.warning("match_topic failed", extra={"error": str(exc)})

        candidates = self._lookup(topic)
        if not candidates and self._list_datasets is not None:
            try:
                candidates = list(self._list_datasets(limit=40) or [])
            except Exception:
                candidates = []
        if not candidates:
            return None
        hits = match_registry(
            topic,
            candidates,
            question=request.question,
            min_confidence=self.min_confidence,
            limit=5,
        )
        return hits[0] if hits else None

    def _lookup(self, topic: str) -> list:
        if self._get_by_topic is None:
            return []
        try:
            results = self._get_by_topic(topic, limit=20)
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

    def _evaluate_record(self, match: MatchScore, topic: str) -> Optional[ProviderHit]:
        meta = _record_to_dict(match.metadata)
        meta["match_confidence"] = match.confidence
        meta["match_explanation"] = match.explanation
        meta["match_reasons"] = list(match.reasons)
        meta["match_components"] = dict(match.components)
        meta["match_rejections"] = list(match.rejections)

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
            from pathlib import Path

            file_ok = Path(local_path).is_file()
            resolved_path = local_path if file_ok else None

        reason = match.explanation or f"Registry match for topic '{topic}'."

        if file_ok:
            logger.info(
                "RegistryProvider high-confidence hit with local file",
                extra={
                    "dataset_id": dataset_id,
                    "topic": topic,
                    "confidence": match.confidence,
                },
            )
            return ProviderHit(
                status=RetrievalStatus.REGISTRY_HIT,
                dataset_id=dataset_id,
                local_path=resolved_path or local_path,
                download_url=download_url,
                metadata=meta,
                reason=reason,
                provider_name=self.name,
            )

        if dataset_id or local_path or download_url:
            if local_path or dataset_id:
                logger.info(
                    "RegistryProvider stale entry (high confidence metadata)",
                    extra={"dataset_id": dataset_id, "topic": topic, "confidence": match.confidence},
                )
                return ProviderHit(
                    status=RetrievalStatus.STALE_REGISTRY_ENTRY,
                    dataset_id=dataset_id,
                    local_path=local_path,
                    download_url=download_url,
                    metadata=meta,
                    reason=reason
                    + " Local library file is missing (stale entry).",
                    provider_name=self.name,
                )

            if download_url:
                return ProviderHit(
                    status=RetrievalStatus.REGISTRY_HIT,
                    dataset_id=dataset_id,
                    local_path=None,
                    download_url=download_url,
                    metadata=meta,
                    reason=reason + " Download URL only (no local file yet).",
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
        "keywords",
        "columns",
        "domain",
        "country",
        "metrics",
        "row_count",
        "date_range",
        "summary",
        "usage_count",
        "checksum",
        "fingerprint",
        "embedding_ref",
    )
    return {k: getattr(record, k, None) for k in keys}
