"""Our World in Data provider — GitHub raw CSV mirrors."""

from __future__ import annotations

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate
from backend.retrieval.data_providers.catalog import catalog_entries_for

_KEYS = {
    "co2", "emission", "emissions", "climate", "energy", "renewable",
    "ev", "electric", "vehicle", "owid", "air", "pollution",
}


class OWIDProvider(DataProvider):
    name = "owid"
    priority = 95

    def supports(self, topic: str, keywords: list[str]) -> bool:
        blob = f"{topic} {' '.join(keywords)}".lower()
        return any(k in blob for k in _KEYS)

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        entries = catalog_entries_for([], keywords)
        out: list[DatasetCandidate] = []
        for e in entries:
            if e.get("provider") != "owid":
                continue
            out.append(
                DatasetCandidate(
                    title=e["title"],
                    topic=topic,
                    download_url=e["download_url"],
                    provider=self.name,
                    source_url=e.get("source_url") or "https://ourworldindata.org",
                    license=e.get("license") or "CC BY 4.0 (OWID)",
                    dataset_version=e.get("dataset_version"),
                    file_format=e.get("file_format") or "csv",
                    description=e.get("description") or "",
                    tags=list(e.get("tags") or []) + ["owid"],
                    rank=110,
                    extra={"source_type": "GitHub", "catalog_key": e.get("catalog_key")},
                )
            )
        out.sort(key=lambda c: c.rank, reverse=True)
        return out[:limit]
