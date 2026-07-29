"""World Bank provider — curated indicators + open CSVs."""

from __future__ import annotations

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate
from backend.retrieval.data_providers.catalog import catalog_entries_for

_WB_KEYS = {
    "gdp", "population", "inflation", "unemployment", "tourism",
    "internet_usage", "internet", "macro", "world bank",
}


class WorldBankProvider(DataProvider):
    name = "world_bank"
    priority = 90

    def supports(self, topic: str, keywords: list[str]) -> bool:
        blob = f"{topic} {' '.join(keywords)}".lower()
        return any(k in blob for k in _WB_KEYS) or bool(
            catalog_entries_for([], keywords)
        )

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        entries = catalog_entries_for([], keywords)
        # Only WB-tagged entries from catalog + explicit macro keys
        out: list[DatasetCandidate] = []
        for e in entries:
            if e.get("provider") not in {"world_bank", "World Bank"} and e.get("catalog_key") not in {
                "gdp", "population", "inflation", "unemployment", "tourism", "internet_usage",
            }:
                # still allow if provider is world_bank
                if e.get("provider") != "world_bank":
                    continue
            out.append(
                DatasetCandidate(
                    title=e["title"],
                    topic=topic,
                    download_url=e["download_url"],
                    provider=self.name,
                    source_url=e.get("source_url") or e["download_url"],
                    license=e.get("license"),
                    dataset_version=e.get("dataset_version"),
                    file_format=e.get("file_format") or "unknown",
                    description=e.get("description") or "",
                    tags=list(e.get("tags") or []) + ["world_bank"],
                    rank=100,
                    extra={"source_type": "API", "catalog_key": e.get("catalog_key")},
                )
            )
        # Direct keyword mapping for common indicators
        indicator_map = {
            "gdp": (
                "NY.GDP.MKTP.CD",
                "World Bank GDP (current US$)",
                "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?format=json&per_page=20000",
            ),
            "population": (
                "SP.POP.TOTL",
                "World Bank Population",
                "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000",
            ),
        }
        blob = f"{topic} {' '.join(keywords)}".lower()
        for key, (code, title, url) in indicator_map.items():
            if key in blob or key in keywords:
                out.append(
                    DatasetCandidate(
                        title=title,
                        topic=topic,
                        download_url=url,
                        provider=self.name,
                        source_url=url,
                        license="CC BY 4.0 (World Bank)",
                        dataset_version=code,
                        file_format="json",
                        description=f"World Bank indicator {code}",
                        tags=[key, "world_bank", "indicator"],
                        rank=80,
                        extra={"source_type": "API", "indicator_id": code},
                    )
                )
        out.sort(key=lambda c: c.rank, reverse=True)
        return out[:limit]
