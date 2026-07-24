"""Hugging Face dataset URL normalizer + HTTP download."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from backend.acquisition.downloaders.base import DatasetDownloader, DownloadPayload
from backend.acquisition.downloaders.http_downloader import HttpDownloader
from backend.acquisition.exceptions import DownloadError


class HuggingFaceDownloader(DatasetDownloader):
    """
    Handles:
      - https://huggingface.co/datasets/{repo}/resolve/main/{file}
      - https://huggingface.co/datasets/{repo}/blob/main/{file}
      - already-resolved HF CDN URLs
    """

    name = "huggingface"

    def __init__(self, http: HttpDownloader | None = None):
        self._http = http or HttpDownloader()

    def can_handle(self, url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return (
            "huggingface.co" in host
            or "hf.co" in host
            or host.endswith("hf-mirror.com")
        )

    def download(self, url: str, *, timeout: int = 60) -> DownloadPayload:
        normalized = self.normalize_url(url)
        # Landing pages without a concrete file cannot be downloaded as a dataset
        if re.match(r"https?://huggingface\.co/datasets/[^/]+/?$", normalized.rstrip("/")):
            raise DownloadError(
                f"Hugging Face URL is a dataset landing page, not a file: {url}"
            )
        return self._http.download(normalized, timeout=timeout)

    @staticmethod
    def normalize_url(url: str) -> str:
        # blob/main/file -> resolve/main/file
        m = re.match(
            r"(https?://huggingface\.co/datasets/[^/]+(?:/[^/]+)?)/blob/([^/]+)/(.+)$",
            url,
        )
        if m:
            base, rev, path = m.group(1), m.group(2), m.group(3)
            return f"{base}/resolve/{rev}/{path}"
        return url
