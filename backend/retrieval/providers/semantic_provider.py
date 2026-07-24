"""Semantic Search provider — Top-K registry candidates by embedding similarity.

Runs after exact Registry match fails. Does not download or write registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from backend.config import settings
from backend.core.logger import get_logger
from backend.retrieval.models import DatasetRequest, ProviderHit, RetrievalStatus
from backend.retrieval.providers.base import RetrievalProvider

logger = get_logger(__name__)


class SemanticProvider(RetrievalProvider):
    """
    Priority step 3: Semantic Search over the Dataset Registry index.

    - search_similar(topic, top_k)
    - accept best hit if score >= threshold
    - enrich with registry metadata + library path when available
    - return SEMANTIC_HIT, else None (continue to Official APIs)
    """

    name = "semantic"

    def __init__(
        self,
        *,
        search_similar: Callable[..., list] | None = None,
        get_by_dataset_id: Callable[..., Any] | None = None,
        dataset_exists: Callable[[str], bool] | None = None,
        get_dataset_path: Callable[[str], Optional[str]] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ):
        self._search_similar = search_similar
        self._get_by_dataset_id = get_by_dataset_id
        self._dataset_exists = dataset_exists
        self._get_dataset_path = get_dataset_path
        self.top_k = int(
            top_k
            if top_k is not None
            else getattr(settings, "SEMANTIC_SEARCH_TOP_K", 5)
        )
        # Cosine / IP score in [0, 1] for normalized embeddings
        self.min_score = float(
            min_score
            if min_score is not None
            else getattr(settings, "SEMANTIC_MIN_SCORE", 0.35)
        )

    def try_retrieve(self, request: DatasetRequest) -> Optional[ProviderHit]:
        topic = request.normalized_topic()
        if not topic or self._search_similar is None:
            return None

        try:
            hits = self._search_similar(
                topic,
                top_k=self.top_k,
                min_score=self.min_score,
            )
        except Exception as exc:
            logger.warning(
                "Semantic search failed; continuing to next provider",
                extra={"error": str(exc), "topic": topic},
            )
            return None

        if not hits:
            logger.info(
                "Semantic search: no candidates above threshold",
                extra={"topic": topic, "min_score": self.min_score},
            )
            return None

        # Evaluate Top-K in score order; pick first usable
        ordered = sorted(
            hits,
            key=lambda h: float(getattr(h, "similarity_score", 0) or 0),
            reverse=True,
        )

        best_below = None
        for hit in ordered:
            score = float(getattr(hit, "similarity_score", 0) or 0)
            if score < self.min_score:
                continue

            registry_id = getattr(hit, "registry_id", None) or (
                hit.get("registry_id") if isinstance(hit, dict) else None
            )
            if not registry_id:
                continue

            meta = self._load_registry_metadata(str(registry_id), hit)
            local_path, file_ok = self._resolve_local(str(registry_id), meta)
            download_url = meta.get("download_url")

            # Prefer candidates we can actually hand to prepare/engineer
            if not file_ok and not download_url:
                best_below = best_below or (score, registry_id, meta)
                continue

            enriched = dict(meta)
            enriched["similarity_score"] = score
            enriched["semantic_candidates"] = [
                {
                    "registry_id": getattr(h, "registry_id", None)
                    or (h.get("registry_id") if isinstance(h, dict) else None),
                    "similarity_score": float(
                        getattr(h, "similarity_score", 0)
                        if not isinstance(h, dict)
                        else h.get("similarity_score") or 0
                    ),
                }
                for h in ordered[: self.top_k]
            ]

            logger.info(
                "SemanticProvider hit",
                extra={
                    "topic": topic,
                    "registry_id": registry_id,
                    "score": score,
                    "local": bool(file_ok),
                },
            )
            return ProviderHit(
                status=RetrievalStatus.SEMANTIC_HIT,
                dataset_id=str(registry_id),
                local_path=local_path if file_ok else meta.get("local_path"),
                download_url=download_url,
                metadata=enriched,
                reason=(
                    f"Semantic match for '{topic}' → registry '{registry_id}' "
                    f"(score={score:.3f}, threshold={self.min_score})."
                ),
                provider_name=self.name,
            )

        # All above-threshold hits lacked path/url — treat as no usable semantic hit
        if best_below:
            logger.info(
                "Semantic candidates above threshold but not usable",
                extra={"topic": topic, "registry_id": best_below[1]},
            )
        return None

    def _load_registry_metadata(self, registry_id: str, hit: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        # Start from semantic hit metadata
        if hasattr(hit, "metadata") and isinstance(hit.metadata, dict):
            meta.update(hit.metadata)
        elif isinstance(hit, dict) and isinstance(hit.get("metadata"), dict):
            meta.update(hit["metadata"])

        if self._get_by_dataset_id is not None:
            try:
                row = self._get_by_dataset_id(registry_id)
                if row is not None:
                    if hasattr(row, "to_dict"):
                        meta = {**meta, **row.to_dict()}
                    elif isinstance(row, dict):
                        meta = {**meta, **row}
                    else:
                        for key in (
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
                            "checksum",
                        ):
                            if hasattr(row, key):
                                meta[key] = getattr(row, key)
            except Exception as exc:
                logger.warning(
                    "Failed to load registry row for semantic hit",
                    extra={"registry_id": registry_id, "error": str(exc)},
                )

        meta["dataset_id"] = registry_id
        return meta

    def _resolve_local(
        self, registry_id: str, meta: dict[str, Any]
    ) -> tuple[Optional[str], bool]:
        if self._dataset_exists is not None:
            try:
                if self._dataset_exists(registry_id):
                    path = None
                    if self._get_dataset_path is not None:
                        path = self._get_dataset_path(registry_id)
                    path = path or meta.get("local_path")
                    if path and Path(str(path)).is_file():
                        return str(path), True
                    if path:
                        return str(path), True
            except Exception:
                pass

        local_path = meta.get("local_path")
        if local_path and Path(str(local_path)).is_file():
            return str(local_path), True
        return (str(local_path) if local_path else None), False
