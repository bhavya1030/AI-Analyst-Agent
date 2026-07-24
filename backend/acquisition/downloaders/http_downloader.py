"""Generic HTTP(S) downloader with retries."""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlparse

import requests

from backend.acquisition.downloaders.base import DatasetDownloader, DownloadPayload
from backend.acquisition.exceptions import DownloadError
from backend.core.logger import get_logger

logger = get_logger(__name__)

USER_AGENT = "AI-Analyst-Agent/1.0 (dataset-acquisition)"


class HttpDownloader(DatasetDownloader):
    name = "http"

    def __init__(self, max_retries: int = 3, backoff_seconds: float = 1.0):
        self.max_retries = max(1, int(max_retries))
        self.backoff_seconds = max(0.1, float(backoff_seconds))

    def can_handle(self, url: str) -> bool:
        try:
            scheme = urlparse(url).scheme.lower()
            return scheme in {"http", "https"}
        except Exception:
            return False

    def download(self, url: str, *, timeout: int = 60) -> DownloadPayload:
        if not self.can_handle(url):
            raise DownloadError(f"HTTP downloader cannot handle URL: {url}")

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    timeout=timeout,
                    headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                    allow_redirects=True,
                    stream=True,
                )
                if response.status_code >= 400:
                    raise DownloadError(
                        f"HTTP {response.status_code} for {url}"
                    )
                # Read body (bounded by response)
                content = response.content
                if content is None:
                    content = b""
                return DownloadPayload(
                    content=content,
                    final_url=str(response.url or url),
                    content_type=response.headers.get("Content-Type"),
                    headers=dict(response.headers),
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "HTTP download attempt failed",
                    extra={"url": url, "attempt": attempt, "error": str(exc)},
                )
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)

        raise DownloadError(f"Failed to download after {self.max_retries} attempts: {last_error}")
