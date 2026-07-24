"""World Bank API / open-data URL downloader."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from backend.acquisition.downloaders.base import DatasetDownloader, DownloadPayload
from backend.acquisition.downloaders.http_downloader import HttpDownloader


class WorldBankDownloader(DatasetDownloader):
    """Handles api.worldbank.org and data.worldbank.org related URLs."""

    name = "world_bank"

    def __init__(self, http: HttpDownloader | None = None):
        self._http = http or HttpDownloader()

    def can_handle(self, url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return (
            "worldbank.org" in host
            or host.endswith("worldbank.org")
        )

    def download(self, url: str, *, timeout: int = 60) -> DownloadPayload:
        normalized = self.normalize_url(url)
        return self._http.download(normalized, timeout=timeout)

    @staticmethod
    def normalize_url(url: str) -> str:
        """Ensure JSON API calls request format=json when hitting v2 API without format."""
        parsed = urlparse(url)
        if "api.worldbank.org" not in parsed.netloc.lower():
            return url
        qs = parse_qs(parsed.query)
        if "format" not in qs and "/v2/" in parsed.path:
            qs["format"] = ["json"]
            new_query = urlencode(qs, doseq=True)
            return urlunparse(parsed._replace(query=new_query))
        return url
