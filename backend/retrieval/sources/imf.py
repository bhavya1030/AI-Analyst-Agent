"""IMF open data — SDMX JSON for common indicators."""

from __future__ import annotations

from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import score_text, topic_tokens

# Public IMF SDMX compact-data style endpoints (JSON-friendly when available).
IMF_ENDPOINTS = {
    "gdp": {
        "title": "IMF IFS / GDP related series",
        "url": "https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/IFS/A..NGDP_R_SA_XDC",
        "description": "IMF International Financial Statistics compact data sample for GDP-related series.",
        "tags": ["imf", "gdp", "ifs"],
    },
    "inflation": {
        "title": "IMF CPI / Inflation",
        "url": "https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/IFS/A..PCPI_IX",
        "description": "IMF CPI index series (SDMX JSON).",
        "tags": ["imf", "inflation", "cpi"],
    },
    "population": {
        "title": "IMF population-related series",
        "url": "https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/IFS/A..LP",
        "description": "IMF population series sample (SDMX JSON).",
        "tags": ["imf", "population"],
    },
}


class IMFSource(DataSource):
    name = "imf"
    source_type = "API"

    def search(self, topic: str, *, limit: int = 5) -> list[SourceCandidate]:
        topic_l = (topic or "").lower()
        tokens = set(topic_tokens(topic))
        hits: list[SourceCandidate] = []

        for key, info in IMF_ENDPOINTS.items():
            if key in topic_l or key in tokens:
                hits.append(
                    SourceCandidate(
                        title=info["title"],
                        topic=topic,
                        download_url=info["url"],
                        source="IMF",
                        source_type=self.source_type,
                        description=info["description"],
                        file_format="json",
                        tags=list(info.get("tags") or []),
                        rank_hint=10 + score_text(topic, info["title"], key),
                    )
                )

        if not hits and tokens:
            hits.append(
                SourceCandidate(
                    title=f"IMF Data Mapper / search: {topic}",
                    topic=topic,
                    download_url="https://www.imf.org/en/Data",
                    source="IMF",
                    source_type="Web",
                    description="IMF data portal landing page for further manual selection.",
                    file_format="unknown",
                    tags=["imf", "portal"],
                    rank_hint=2,
                )
            )

        hits.sort(key=lambda c: c.rank_hint, reverse=True)
        return hits[:limit]
