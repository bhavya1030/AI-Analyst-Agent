"""CSV URL provider — accepts explicit direct CSV/XLSX/Parquet links in the query."""

from __future__ import annotations

import re

from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate
from backend.retrieval.data_providers.validation import is_blocked_url, looks_like_file_url

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)


class CsvUrlProvider(DataProvider):
    name = "csv_url"
    priority = 100

    def supports(self, topic: str, keywords: list[str]) -> bool:
        return bool(_URL_RE.search(topic or ""))

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        urls = _URL_RE.findall(topic or "")
        out: list[DatasetCandidate] = []
        for url in urls:
            url = url.rstrip(").,];")
            blocked, _ = is_blocked_url(url)
            if blocked:
                continue
            if not looks_like_file_url(url) and not any(
                ext in url.lower() for ext in (".csv", ".json", ".xlsx", ".parquet", ".zip")
            ):
                continue
            fmt = "csv"
            lower = url.lower().split("?")[0]
            for ext in ("parquet", "xlsx", "xls", "json", "csv", "zip"):
                if lower.endswith("." + ext):
                    fmt = ext
                    break
            out.append(
                DatasetCandidate(
                    title=f"Direct file URL ({fmt})",
                    topic=topic,
                    download_url=url,
                    provider=self.name,
                    source_url=url,
                    license="as published by source",
                    file_format=fmt,
                    description="User- or query-supplied direct download URL.",
                    tags=["direct_url", fmt],
                    rank=120,
                    extra={"source_type": "UserURL"},
                )
            )
        return out[:limit]
