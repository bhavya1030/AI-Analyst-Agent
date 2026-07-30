"""JSON API provider — CoinGecko and other structured JSON endpoints."""

from __future__ import annotations

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate
from backend.retrieval.data_providers.catalog import catalog_entries_for


class JsonApiProvider(DataProvider):
    name = "json_api"
    priority = 75

    def supports(self, topic: str, keywords: list[str]) -> bool:
        blob = f"{topic} {' '.join(keywords)}".lower()
        return any(k in blob for k in ("bitcoin", "crypto", "cryptocurrency", "ethereum", "json"))

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        out: list[DatasetCandidate] = []
        for e in catalog_entries_for([], keywords):
            if e.get("provider") != "json_api" and e.get("file_format") != "json":
                if e.get("provider") not in {"json_api"}:
                    continue
            if e.get("provider") not in {"json_api"}:
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
                    file_format="json",
                    description=e.get("description") or "",
                    tags=list(e.get("tags") or []) + ["json_api"],
                    rank=95,
                    extra={"source_type": "API", "catalog_key": e.get("catalog_key")},
                )
            )
        # Explicit coingecko if crypto keywords
        blob = f"{topic} {' '.join(keywords)}".lower()
        if any(k in blob for k in ("bitcoin", "crypto", "cryptocurrency")):
            out.append(
                DatasetCandidate(
                    title="Bitcoin USD market chart (CoinGecko)",
                    topic=topic,
                    download_url=(
                        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
                        "?vs_currency=usd&days=365"
                    ),
                    provider=self.name,
                    source_url="https://www.coingecko.com",
                    license="CoinGecko API terms",
                    dataset_version="coingecko-bitcoin-365d",
                    file_format="json",
                    description="Bitcoin price/volume history as JSON.",
                    tags=["bitcoin", "crypto", "json"],
                    rank=96,
                    extra={"source_type": "API"},
                )
            )
        out.sort(key=lambda c: c.rank, reverse=True)
        return out[:limit]
