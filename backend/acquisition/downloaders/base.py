"""Abstract downloader interface for Dataset Acquisition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class DownloadPayload:
    content: bytes
    final_url: str
    content_type: Optional[str] = None
    headers: Optional[dict] = None


class DatasetDownloader(ABC):
    """Fetches raw bytes for a URL. Does not save or parse into DataFrames."""

    name: str = "base"

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        ...

    @abstractmethod
    def download(self, url: str, *, timeout: int = 60) -> DownloadPayload:
        ...
