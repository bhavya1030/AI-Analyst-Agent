"""Caching layer: process RAM (dataset frames) + durable AnalysisCache."""

from backend.cache.analysis_cache import (
    KIND_CHART,
    KIND_EDA,
    KIND_EMBEDDING,
    KIND_FORECAST,
    KIND_PROFILE,
    AnalysisCache,
    AnalysisCacheService,
    ensure_analysis_cache_table,
    get_analysis_cache,
)
from backend.cache.fingerprint import compute_dataset_fingerprint, fingerprint_dataframe

__all__ = [
    "AnalysisCache",
    "AnalysisCacheService",
    "get_analysis_cache",
    "ensure_analysis_cache_table",
    "compute_dataset_fingerprint",
    "fingerprint_dataframe",
    "KIND_EDA",
    "KIND_PROFILE",
    "KIND_EMBEDDING",
    "KIND_FORECAST",
    "KIND_CHART",
]
