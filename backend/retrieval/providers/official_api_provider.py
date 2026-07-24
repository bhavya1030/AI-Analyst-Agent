"""Official API provider — World Bank, OECD, IMF."""

from __future__ import annotations

from typing import Iterable, Optional

from backend.core.logger import get_logger
from backend.retrieval.models import DatasetRequest, ProviderHit, RetrievalStatus
from backend.retrieval.providers.base import RetrievalProvider
from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import is_loadable_url
from backend.retrieval.sources import OFFICIAL_SOURCES

logger = get_logger(__name__)


class OfficialApiProvider(RetrievalProvider):
    """Priority step 3: official statistical APIs / curated official feeds."""

    name = "official_api"

    def __init__(self, sources: Optional[Iterable[DataSource]] = None):
        self._sources = list(sources) if sources is not None else list(OFFICIAL_SOURCES)

    def try_retrieve(self, request: DatasetRequest) -> Optional[ProviderHit]:
        topic = request.normalized_topic()
        if not topic:
            return None

        candidates: list[SourceCandidate] = []
        for source in self._sources:
            try:
                found = source.search(topic, limit=5) or []
                candidates.extend(found)
            except Exception as exc:
                logger.warning(
                    "Official source failed",
                    extra={"source": getattr(source, "name", "?"), "error": str(exc)},
                )

        if not candidates:
            return None

        best = _pick_best(candidates)
        if best is None:
            return None

        meta = best.to_metadata_dict()
        status = RetrievalStatus.API_HIT
        logger.info(
            "OfficialApiProvider hit",
            extra={"topic": topic, "source": best.source, "url": best.download_url},
        )
        return ProviderHit(
            status=status,
            dataset_id=None,
            local_path=None,
            download_url=best.download_url,
            metadata=meta,
            reason=f"Official API/source match via {best.source}.",
            provider_name=f"{self.name}:{best.source}",
        )


def _pick_best(candidates: list[SourceCandidate]) -> Optional[SourceCandidate]:
    if not candidates:
        return None
    # Prefer loadable tabular URLs, then rank_hint
    ranked = sorted(
        candidates,
        key=lambda c: (
            1 if is_loadable_url(c.download_url) else 0,
            int(c.rank_hint or 0),
        ),
        reverse=True,
    )
    return ranked[0]
