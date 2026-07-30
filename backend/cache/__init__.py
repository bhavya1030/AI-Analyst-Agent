"""Caching layer: process RAM (dataset frames) + durable AnalysisCache + ask cache."""

from backend.cache.analysis_cache import (
    KIND_ASK,
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
from backend.cache.ask_cache import (
    AskCacheService,
    get_ask_cache,
    normalize_question,
    primary_intent,
    reset_ask_cache_stats,
    resolve_dataset_fingerprint,
)
from backend.cache.fingerprint import compute_dataset_fingerprint, fingerprint_dataframe

__all__ = [
    "AnalysisCache",
    "AnalysisCacheService",
    "AskCacheService",
    "get_analysis_cache",
    "get_ask_cache",
    "ensure_analysis_cache_table",
    "compute_dataset_fingerprint",
    "fingerprint_dataframe",
    "normalize_question",
    "primary_intent",
    "resolve_dataset_fingerprint",
    "reset_ask_cache_stats",
    "KIND_EDA",
    "KIND_PROFILE",
    "KIND_EMBEDDING",
    "KIND_FORECAST",
    "KIND_CHART",
    "KIND_ASK",
]
