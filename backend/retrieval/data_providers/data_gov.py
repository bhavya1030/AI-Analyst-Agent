"""Data.gov provider — CKAN resource search returning only direct resource downloads."""

from __future__ import annotations

from backend.core.logger import get_logger
from backend.retrieval.data_providers.base import DataProvider, DatasetCandidate
from backend.retrieval.sources.common import http_get_json

logger = get_logger(__name__)

_CKAN = "https://catalog.data.gov/api/3/action/package_search"
_FILE_EXTS = (".csv", ".json", ".xlsx", ".xls", ".parquet", ".zip")


class DataGovProvider(DataProvider):
    name = "data_gov"
    priority = 70

    def supports(self, topic: str, keywords: list[str]) -> bool:
        # General open-data fallback for US public topics
        return True

    def search(self, topic: str, keywords: list[str], *, limit: int = 5) -> list[DatasetCandidate]:
        q = " ".join(keywords[:6]) or topic
        payload = http_get_json(_CKAN, params={"q": q, "rows": min(limit * 3, 12)})
        if not payload or not isinstance(payload, dict):
            return []
        result = payload.get("result") or {}
        results = result.get("results") or []
        out: list[DatasetCandidate] = []
        for pkg in results:
            if not isinstance(pkg, dict):
                continue
            title = str(pkg.get("title") or "data.gov dataset")
            resources = pkg.get("resources") or []
            for res in resources:
                if not isinstance(res, dict):
                    continue
                url = (res.get("url") or "").strip()
                if not url:
                    continue
                lower = url.lower().split("?")[0]
                fmt = (res.get("format") or "").lower()
                if not (
                    any(lower.endswith(ext) for ext in _FILE_EXTS)
                    or fmt in {"csv", "json", "xlsx", "xls", "parquet", "zip"}
                ):
                    continue
                # Skip HTML landing
                if "catalog.data.gov/dataset/" in lower and not any(
                    lower.endswith(ext) for ext in _FILE_EXTS
                ):
                    continue
                file_format = fmt if fmt in {"csv", "json", "xlsx", "xls", "parquet", "zip"} else (
                    next((ext.lstrip(".") for ext in _FILE_EXTS if lower.endswith(ext)), "unknown")
                )
                out.append(
                    DatasetCandidate(
                        title=f"{title} ({res.get('name') or file_format})",
                        topic=topic,
                        download_url=url,
                        provider=self.name,
                        source_url=pkg.get("url") or url,
                        license=str(pkg.get("license_title") or pkg.get("license_id") or "data.gov"),
                        dataset_version=str(pkg.get("id") or ""),
                        file_format=file_format,
                        description=str(pkg.get("notes") or "")[:300],
                        tags=["data.gov", file_format],
                        rank=55,
                        extra={"source_type": "data.gov", "package_id": pkg.get("id")},
                    )
                )
                if len(out) >= limit:
                    return out
        return out[:limit]
