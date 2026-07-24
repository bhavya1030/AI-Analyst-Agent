"""Modular downloaders for Dataset Acquisition."""

from backend.acquisition.downloaders.base import DatasetDownloader, DownloadPayload
from backend.acquisition.downloaders.github_raw_downloader import GitHubRawDownloader
from backend.acquisition.downloaders.http_downloader import HttpDownloader
from backend.acquisition.downloaders.huggingface_downloader import HuggingFaceDownloader
from backend.acquisition.downloaders.world_bank_downloader import WorldBankDownloader

__all__ = [
    "DatasetDownloader",
    "DownloadPayload",
    "HttpDownloader",
    "GitHubRawDownloader",
    "HuggingFaceDownloader",
    "WorldBankDownloader",
]
