"""External open-data sources for Official API + Internet Search providers."""

from backend.retrieval.sources.base import DataSource, SourceCandidate
from backend.retrieval.sources.github import GitHubSource
from backend.retrieval.sources.huggingface import HuggingFaceSource
from backend.retrieval.sources.imf import IMFSource
from backend.retrieval.sources.oecd import OECDSource
from backend.retrieval.sources.wikipedia import WikipediaSource
from backend.retrieval.sources.world_bank import WorldBankSource

OFFICIAL_SOURCES: list[DataSource] = [
    WorldBankSource(),
    OECDSource(),
    IMFSource(),
]

INTERNET_SOURCES: list[DataSource] = [
    GitHubSource(),
    HuggingFaceSource(),
    WikipediaSource(),
]

ALL_SOURCES: list[DataSource] = OFFICIAL_SOURCES + INTERNET_SOURCES

__all__ = [
    "DataSource",
    "SourceCandidate",
    "WorldBankSource",
    "GitHubSource",
    "HuggingFaceSource",
    "OECDSource",
    "IMFSource",
    "WikipediaSource",
    "OFFICIAL_SOURCES",
    "INTERNET_SOURCES",
    "ALL_SOURCES",
]
