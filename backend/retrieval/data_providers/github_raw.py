"""GitHub raw CSV provider — curated raw.githubusercontent.com only."""

from __future__ import annotations

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate
from backend.retrieval.data_providers.catalog import catalog_entries_for, CURATED

# Additional trusted raw paths
_EXTRA = {
    "gold": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
    "covid": "https://raw.githubusercontent.com/datasets/covid-19/master/data/countries-aggregated.csv",
    "olympics": (
        "https://raw.githubusercontent.com/rfordatascience/tidytuesday/"
        "master/data/2021/2021-07-27/olympics.csv"
    ),
    "climate": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
}


class GitHubRawProvider(DataProvider):
    name = "github_raw"
    priority = 85

    def supports(self, topic: str, keywords: list[str]) -> bool:
        return True  # always eligible as fallback for curated github entries

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        out: list[DatasetCandidate] = []
        for e in catalog_entries_for([], keywords):
            if e.get("provider") != "github_raw":
                continue
            out.append(_from_entry(topic, e, rank=90))

        blob = f"{topic} {' '.join(keywords)}".lower()
        for key, url in _EXTRA.items():
            if key in blob or key in keywords:
                out.append(
                    DatasetCandidate(
                        title=f"GitHub raw dataset ({key})",
                        topic=topic,
                        download_url=url,
                        provider=self.name,
                        source_url=url,
                        license="ODC-PDDL / upstream",
                        dataset_version=f"datasets/{key}",
                        file_format="csv",
                        description=f"Curated GitHub raw CSV for {key}",
                        tags=[key, "github", "csv"],
                        rank=88,
                        extra={"source_type": "GitHub"},
                    )
                )
        # Also surface GDP/population raw if keywords match (redundant safe fallback)
        for key in ("gdp", "population"):
            if key in blob or key in keywords:
                for e in CURATED.get(key, []):
                    out.append(_from_entry(topic, e, rank=86))

        # de-dupe by URL
        seen: set[str] = set()
        unique: list[DatasetCandidate] = []
        for c in sorted(out, key=lambda x: x.rank, reverse=True):
            if c.download_url in seen:
                continue
            seen.add(c.download_url)
            unique.append(c)
        return unique[:limit]


def _from_entry(topic: str, e: dict, *, rank: int) -> DatasetCandidate:
    return DatasetCandidate(
        title=e["title"],
        topic=topic,
        download_url=e["download_url"],
        provider="github_raw",
        source_url=e.get("source_url") or e["download_url"],
        license=e.get("license"),
        dataset_version=e.get("dataset_version"),
        file_format=e.get("file_format") or "csv",
        description=e.get("description") or "",
        tags=list(e.get("tags") or []) + ["github"],
        rank=rank,
        extra={"source_type": "GitHub", "catalog_key": e.get("catalog_key")},
    )
