"""Internet search provider — GitHub, HuggingFace, Wikipedia."""

from __future__ import annotations

from typing import Iterable, Optional

from backend.core.logger import get_logger
from backend.retrieval.models import DatasetRequest, ProviderHit, RetrievalStatus
from backend.retrieval.providers.base import RetrievalProvider
from backend.retrieval.sources import INTERNET_SOURCES
from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import is_loadable_url

logger = get_logger(__name__)


class InternetSearchProvider(RetrievalProvider):
    """Priority step 4: open web / community dataset catalogs."""

    name = "internet_search"

    def __init__(self, sources: Optional[Iterable[DataSource]] = None):
        self._sources = list(sources) if sources is not None else list(INTERNET_SOURCES)

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
                    "Internet source failed",
                    extra={"source": getattr(source, "name", "?"), "error": str(exc)},
                )

        if not candidates:
            return None

        best = _pick_best(candidates)
        if best is None:
            return None

        meta = best.to_metadata_dict()
        # Attach alternate candidates for callers (not a DataFrame)
        meta["candidates"] = [
            {
                "title": c.title,
                "source": c.source,
                "download_url": c.download_url,
                "rank_hint": c.rank_hint,
            }
            for c in sorted(candidates, key=lambda x: x.rank_hint, reverse=True)[:5]
        ]

        logger.info(
            "InternetSearchProvider hit",
            extra={"topic": topic, "source": best.source, "url": best.download_url},
        )
        return ProviderHit(
            status=RetrievalStatus.INTERNET_HIT,
            dataset_id=None,
            local_path=None,
            download_url=best.download_url,
            metadata=meta,
            reason=f"Internet/open-data match via {best.source}.",
            provider_name=f"{self.name}:{best.source}",
        )


def _pick_best(candidates: list[SourceCandidate]) -> Optional[SourceCandidate]:
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda c: (
            1 if is_loadable_url(c.download_url) else 0,
            int(c.rank_hint or 0),
        ),
        reverse=True,
    )
    return ranked[0]
