"""GitHub raw / blob URL normalizer + HTTP download."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from backend.acquisition.downloaders.base import DatasetDownloader, DownloadPayload
from backend.acquisition.downloaders.http_downloader import HttpDownloader


class GitHubRawDownloader(DatasetDownloader):
    """Handles github.com blob/tree and raw.githubusercontent.com URLs."""

    name = "github_raw"

    def __init__(self, http: HttpDownloader | None = None):
        self._http = http or HttpDownloader()

    def can_handle(self, url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return host in {
            "raw.githubusercontent.com",
            "github.com",
            "www.github.com",
            "gist.githubusercontent.com",
        }

    def download(self, url: str, *, timeout: int = 60) -> DownloadPayload:
        normalized = self.normalize_url(url)
        return self._http.download(normalized, timeout=timeout)

    @staticmethod
    def normalize_url(url: str) -> str:
        """Convert github blob URLs to raw.githubusercontent.com when possible."""
        # Already raw
        if "raw.githubusercontent.com" in url or "gist.githubusercontent.com" in url:
            return url

        # https://github.com/{user}/{repo}/blob/{branch}/path/to/file.csv
        m = re.match(
            r"https?://(www\.)?github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$",
            url,
        )
        if m:
            user, repo, branch, path = m.group(2), m.group(3), m.group(4), m.group(5)
            return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"

        # https://github.com/{user}/{repo}/raw/{branch}/path
        m2 = re.match(
            r"https?://(www\.)?github\.com/([^/]+)/([^/]+)/raw/([^/]+)/(.+)$",
            url,
        )
        if m2:
            user, repo, branch, path = m2.group(2), m2.group(3), m2.group(4), m2.group(5)
            return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"

        return url
