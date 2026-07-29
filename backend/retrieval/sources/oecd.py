"""OECD open data — only structured SDMX JSON endpoints (never HTML search pages)."""

from __future__ import annotations

from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import score_text, topic_tokens

# Well-known OECD SDMX endpoints (JSON) for common macro topics.
# NOTE: Do NOT return data.oecd.org/searchresults HTML pages — they are not datasets.
OECD_ENDPOINTS = {
    "gdp": {
        "title": "OECD GDP (SDMX JSON)",
        "url": "https://stats.oecd.org/SDMX-JSON/data/QNA/AUS+USA+GBR+DEU+FRA+JPN+CAN.B1_GE.VOBARSA.Q/all?startTime=2015",
        "description": "OECD Quarterly National Accounts GDP-style SDMX JSON endpoint.",
        "tags": ["oecd", "gdp", "macro"],
    },
    "unemployment": {
        "title": "OECD Unemployment (SDMX JSON)",
        "url": "https://stats.oecd.org/SDMX-JSON/data/STLABOUR/AUS+USA.LRHUTTTT.STSA.M/all?startTime=2018",
        "description": "OECD labour statistics SDMX JSON endpoint.",
        "tags": ["oecd", "unemployment", "labour"],
    },
    "inflation": {
        "title": "OECD Inflation / CPI (SDMX JSON)",
        "url": "https://stats.oecd.org/SDMX-JSON/data/PRICES_CPI/AUS+USA.CPALTT01.IXOB.M/all?startTime=2018",
        "description": "OECD consumer prices SDMX JSON endpoint.",
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

        # Intentionally no HTML searchresults fallback.
        hits.sort(key=lambda c: c.rank_hint, reverse=True)
        return hits[:limit]
