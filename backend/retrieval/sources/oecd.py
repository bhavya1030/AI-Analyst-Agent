"""OECD open data — SDMX/JSON API probes for known topics."""

from __future__ import annotations

from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import score_text, topic_tokens

# Well-known OECD SDMX endpoints (JSON) for common macro topics.
OECD_ENDPOINTS = {
    "gdp": {
        "title": "OECD GDP (SDMX JSON)",
        "url": "https://stats.oecd.org/SDMX-JSON/data/QNA/all/all",
        "description": "OECD Quarterly National Accounts style endpoint (JSON).",
        "tags": ["oecd", "gdp", "macro"],
    },
    "unemployment": {
        "title": "OECD Unemployment",
        "url": "https://stats.oecd.org/SDMX-JSON/data/STLABOUR/all/all",
        "description": "OECD labour statistics endpoint (JSON).",
        "tags": ["oecd", "unemployment", "labour"],
    },
    "inflation": {
        "title": "OECD Inflation / CPI",
        "url": "https://stats.oecd.org/SDMX-JSON/data/PRICES_CPI/all/all",
        "description": "OECD consumer prices endpoint (JSON).",
        "tags": ["oecd", "inflation", "cpi"],
    },
}


class OECDSource(DataSource):
    name = "oecd"
    source_type = "API"

    def search(self, topic: str, *, limit: int = 5) -> list[SourceCandidate]:
        topic_l = (topic or "").lower()
        tokens = set(topic_tokens(topic))
        hits: list[SourceCandidate] = []

        for key, info in OECD_ENDPOINTS.items():
            if key in topic_l or key in tokens:
                hits.append(
                    SourceCandidate(
                        title=info["title"],
                        topic=topic,
                        download_url=info["url"],
                        source="OECD",
                        source_type=self.source_type,
                        description=info["description"],
                        file_format="json",
                        tags=list(info.get("tags") or []),
                        rank_hint=10 + score_text(topic, info["title"], key),
                    )
                )

        # Generic OECD topic page (not always loadable tabular)
        if not hits and tokens:
            hits.append(
                SourceCandidate(
                    title=f"OECD search: {topic}",
                    topic=topic,
                    download_url=f"https://data.oecd.org/searchresults/?q={'+'.join(list(tokens)[:5])}",
                    source="OECD",
                    source_type="Web",
                    description="OECD data search landing page (may require further resource selection).",
                    file_format="unknown",
                    tags=["oecd", "search"],
                    rank_hint=3 + score_text(topic, topic),
                )
            )

        hits.sort(key=lambda c: c.rank_hint, reverse=True)
        return hits[:limit]
