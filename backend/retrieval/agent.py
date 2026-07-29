"""Dataset Retrieval Agent — decides where data should come from.

Does NOT download, clean, analyze, visualize, or mutate registry/library.
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.core.logger import get_logger
from backend.retrieval.exceptions import RetrievalValidationError
from backend.retrieval.models import (
    DatasetRequest,
    NextAction,
    ProviderHit,
    RetrievalResult,
    RetrievalStatus,
)
from backend.retrieval.providers.base import RetrievalProvider

logger = get_logger(__name__)


class DatasetRetrievalAgent:
    """
    Orchestrates providers in priority order:

      1. SessionProvider
      2. RegistryProvider (exact/topic match)
      3. SemanticProvider (embedding similarity over registry index)
      4. OpenDataProvider (multi-provider chain: World Bank, OWID, GitHub raw,
         JSON APIs, data.gov, Hugging Face, direct CSV URLs — with validation)
      5. UserUploadProvider (placeholder)

    If nothing resolves: SEARCH_REQUIRED.
    """

    def __init__(self, providers: Optional[Iterable[RetrievalProvider]] = None):
        self._providers = list(providers) if providers is not None else []

    def retrieve(self, request: DatasetRequest | dict) -> RetrievalResult:
        req = self._normalize_request(request)
        topic = req.normalized_topic()
        if not topic:
            raise RetrievalValidationError("topic is required")

        logger.info(
            "DatasetRetrievalAgent start",
            extra={"topic": topic, "session_id": req.session_id, "force_new": req.force_new_topic},
        )

        for provider in self._providers:
            try:
                hit = provider.try_retrieve(req)
            except Exception as exc:
                logger.warning(
                    "Provider failed; continuing",
                    extra={"provider": getattr(provider, "name", "?"), "error": str(exc)},
                )
                continue

            if hit is None:
                continue

            result = self._to_result(hit, topic)
            logger.info(
                "DatasetRetrievalAgent decision",
                extra={
                    "status": result.status.value,
                    "provider": result.provider,
                    "topic": topic,
                    "next_action": result.next_action.value,
                },
            )
            return result

        # No provider answered — internet search is required (not performed here).
        return RetrievalResult.search_required(
            topic,
            reason=(
                f"No session or registry dataset for topic '{topic}'. "
                "Internet search is required (not implemented in this agent)."
            ),
        )

    def _normalize_request(self, request: DatasetRequest | dict) -> DatasetRequest:
        if isinstance(request, DatasetRequest):
            return request
        if isinstance(request, dict):
            return DatasetRequest.from_dict(request)
        raise RetrievalValidationError("request must be DatasetRequest or dict")

    def _to_result(self, hit: ProviderHit, topic: str) -> RetrievalResult:
        next_action = _next_action_for_status(hit.status, hit)
        return RetrievalResult(
            status=hit.status,
            dataset_id=hit.dataset_id,
            local_path=hit.local_path,
            metadata=hit.metadata,
            reason=hit.reason,
            next_action=next_action,
            download_url=hit.download_url,
            provider=hit.provider_name,
            topic=topic,
        )


def _next_action_for_status(status: RetrievalStatus, hit: ProviderHit) -> NextAction:
    if status == RetrievalStatus.SESSION_HIT:
        return NextAction.USE_SESSION
    if status in (RetrievalStatus.REGISTRY_HIT, RetrievalStatus.SEMANTIC_HIT):
        if hit.local_path:
            return NextAction.USE_LOCAL_FILE
        if hit.download_url:
            return NextAction.USE_DOWNLOAD_URL
        return NextAction.USE_LOCAL_FILE
    if status in (RetrievalStatus.API_HIT, RetrievalStatus.INTERNET_HIT):
        if hit.local_path:
            return NextAction.USE_LOCAL_FILE
        if hit.download_url:
            return NextAction.USE_DOWNLOAD_URL
        return NextAction.ASK_USER_UPLOAD
    if status == RetrievalStatus.STALE_REGISTRY_ENTRY:
        # Do not auto-search; surface stale so caller can re-fetch or search later
        if hit.download_url:
            return NextAction.USE_DOWNLOAD_URL
        return NextAction.RUN_INTERNET_SEARCH
    if status == RetrievalStatus.SEARCH_REQUIRED:
        return NextAction.RUN_INTERNET_SEARCH
    if status == RetrievalStatus.NOT_FOUND:
        return NextAction.ASK_USER_UPLOAD
    return NextAction.NONE
