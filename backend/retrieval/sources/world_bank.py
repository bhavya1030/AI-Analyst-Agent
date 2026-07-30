"""World Bank open data shortcuts + indicator-style mapping."""

from __future__ import annotations

from backend.config import settings
from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.common import guess_format, is_loadable_url, score_text, topic_tokens

# Curated loadable CSVs commonly used with World Bank / open macro topics.
WORLD_BANK_RAW = {
    "gdp": {
        "title": "World Bank GDP (open CSV)",
        "url": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
        "description": "Country-level annual GDP series suitable for trend analysis.",
        "tags": ["gdp", "macro", "world bank"],
    },
    "population": {
        "title": "World Population by Country",
        "url": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
        "description": "Country population totals for demographic analysis.",
        "tags": ["population", "demographics"],
    },
    "inflation": {
        "title": "Global CPI / Inflation (World Bank API)",
        "url": (
            "https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL.ZG"
            "?format=json&per_page=20000"
        ),
        "description": "Consumer price inflation series from World Bank indicators.",
        "tags": ["inflation", "cpi"],
    },
}


class WorldBankSource(DataSource):
    name = "world_bank"
    source_type = "API"

    def search(self, topic: str, *, limit: int = 5) -> list[SourceCandidate]:
        topic_l = (topic or "").lower()
        tokens = set(topic_tokens(topic))
        hits: list[SourceCandidate] = []

        # Configured official-ish sources
        for key, url in (settings.DATASET_SOURCES or {}).items():
            if key in topic_l or key in tokens:
                hits.append(
                    SourceCandidate(
                        title=f"World Bank / open {key.upper()}",
                        topic=topic,
                        download_url=url if is_loadable_url(url) else url,
                        source="World Bank",
                        source_type=self.source_type,
                        description=f"Open dataset for {key}",
                        file_format=guess_format(url),
                        tags=[key, "world bank"],
                        rank_hint=12 + score_text(topic, key, url),
                    )
                )

        for key, info in WORLD_BANK_RAW.items():
            if key in topic_l or key in tokens:
                url = info["url"]
                hits.append(
                    SourceCandidate(
                        title=info["title"],
                        topic=topic,
                        download_url=url,
                        source="World Bank",
                        source_type=self.source_type,
                        description=info["description"],
                        file_format=guess_format(url),
                        tags=list(info.get("tags") or []),
                        rank_hint=14 + score_text(topic, info["title"], info["description"]),
                    )
                )

        # Light API probe for indicator search (metadata only; may not be raw CSV)
        if not hits and tokens:
            # World Bank API: search indicators — landing/API JSON, not always tabular file
            query = "+".join(list(tokens)[:4])
            from backend.retrieval.sources.common import http_get_json

            payload = http_get_json(
                "https://api.worldbank.org/v2/indicator",
                params={"format": "json", "per_page": min(limit, 5), "q": query},
            )
            # Response shape: [meta, [indicators...]] when successful
            if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
                for item in payload[1][:limit]:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name") or item.get("id") or "World Bank indicator"
                    ind_id = item.get("id") or ""
                    # Prefer a documented CSV-friendly bulk pattern when id known
                    api_url = (
                        f"https://api.worldbank.org/v2/country/all/indicator/{ind_id}"
                        f"?format=json&per_page=20000"
                        if ind_id
                        else None
                    )
                    hits.append(
                        SourceCandidate(
                            title=str(name)[:120],
                            topic=topic,
                            download_url=api_url,
                            source="World Bank",
                            source_type=self.source_type,
                            description=str(item.get("sourceNote") or item.get("sourceOrganization") or "")[:300],
                            file_format="json",
                            tags=["world bank", "indicator", ind_id.lower()],
                            rank_hint=6 + score_text(topic, name),
                            extra={"indicator_id": ind_id},
                        )
                    )

        hits.sort(key=lambda c: c.rank_hint, reverse=True)
        return hits[:limit]
