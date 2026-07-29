"""Open-data retrieval provider — multi-provider orchestrator with validation."""

from __future__ import annotations

from typing import Optional

from backend.core.logger import get_logger
from backend.retrieval.data_providers.orchestrator import (
    ProviderOrchestrator,
    get_provider_orchestrator,
)
from backend.retrieval.models import DatasetRequest, ProviderHit, RetrievalStatus
from backend.retrieval.providers.base import RetrievalProvider

logger = get_logger(__name__)


class OpenDataProvider(RetrievalProvider):
    """
    Replaces fragile Official API + Internet HTML search paths.

    Uses ProviderOrchestrator:
      topic → provider selection → search → validate download URL → hit
    """

    name = "open_data"

    def __init__(self, orchestrator: ProviderOrchestrator | None = None):
        self._orchestrator = orchestrator or get_provider_orchestrator()

    def try_retrieve(self, request: DatasetRequest) -> Optional[ProviderHit]:
        topic = request.normalized_topic()
        if not topic:
            return None

        result = self._orchestrator.resolve(topic)
        if not result.success or not result.candidate:
            logger.info(
                "OpenDataProvider miss",
                extra={
                    "topic": topic,
                    "failure_reason": result.failure_reason,
                    "retry_count": result.retry_count,
                    "providers_tried": result.providers_tried,
                },
            )
            # Return None so agent can fall through; if this is last provider,
            # agent emits SEARCH_REQUIRED.
            return None

        cand = result.candidate
        meta = cand.to_metadata()
        meta["orchestrator"] = {
            "providers_tried": result.providers_tried,
            "retry_count": result.retry_count,
            "total_ms": result.total_ms,
            "validation": result.validation,
            "attempts": result.attempts[-8:],  # tail for debug
        }
        meta["download_url"] = cand.download_url
        meta["source_url"] = cand.source_url or cand.download_url
        meta["provider"] = cand.provider
        meta["license"] = cand.license
        meta["dataset_version"] = cand.dataset_version

        status = (
            RetrievalStatus.API_HIT
            if cand.provider in {"world_bank", "json_api", "owid"}
            else RetrievalStatus.INTERNET_HIT
        )

        logger.info(
            "OpenDataProvider hit",
            extra={
                "topic": topic,
                "provider": cand.provider,
                "url": cand.download_url,
                "retry_count": result.retry_count,
                "total_ms": result.total_ms,
            },
        )
        return ProviderHit(
            status=status,
            dataset_id=None,
            local_path=None,
            download_url=cand.download_url,
            metadata=meta,
            reason=(
                f"Validated open-data match via provider '{cand.provider}' "
                f"after {result.retry_count} retries."
            ),
            provider_name=f"{self.name}:{cand.provider}",
        )
