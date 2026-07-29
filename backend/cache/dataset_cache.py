"""Process-local dataset frame cache + bridges to durable AnalysisCache.

DataFrames stay in RAM only (not SQLite). Profile / forecast / embedding
lookups prefer durable fingerprint-based entries when a fingerprint is
provided; reference-keyed RAM maps remain for backward compatibility.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import pandas as pd

from backend.cache.analysis_cache import (
    KIND_EMBEDDING,
    KIND_FORECAST,
    KIND_PROFILE,
    get_analysis_cache,
)
from backend.core.logger import get_logger

logger = get_logger(__name__)

CACHE_MAX_ENTRIES = 64

_dataset_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
_profile_cache: dict[str, dict[str, Any]] = {}
_forecast_cache: dict[str, dict[str, Any]] = {}
_embedding_cache: dict[str, Any] = {}
# reference → last known fingerprint (for L1 reference lookups after durable store)
_ref_fingerprints: dict[str, str] = {}


def _trim_cache(cache: OrderedDict, max_entries: int = CACHE_MAX_ENTRIES) -> None:
    while len(cache) > max_entries:
        cache.popitem(last=False)


def get_dataset(reference: str) -> pd.DataFrame | None:
    if reference in _dataset_cache:
        value = _dataset_cache.pop(reference)
        _dataset_cache[reference] = value
        return value
    return None


def set_dataset(reference: str, dataset: pd.DataFrame) -> None:
    _dataset_cache[reference] = dataset
    _trim_cache(_dataset_cache)


def remember_fingerprint(reference: str | None, fingerprint: str | None) -> None:
    if reference and fingerprint:
        _ref_fingerprints[reference] = fingerprint


def get_profile(
    reference: str | None = None,
    *,
    fingerprint: str | None = None,
) -> dict[str, Any] | None:
    if reference and reference in _profile_cache:
        return _profile_cache.get(reference)

    fp = fingerprint or (reference and _ref_fingerprints.get(reference))
    if fp:
        try:
            payload = get_analysis_cache().get(KIND_PROFILE, fp)
            if isinstance(payload, dict):
                if reference:
                    _profile_cache[reference] = payload
                return payload
        except Exception as exc:
            logger.debug("Durable profile get failed", extra={"error": str(exc)})
    return None


def set_profile(
    reference: str | None,
    profile: dict[str, Any],
    *,
    fingerprint: str | None = None,
) -> None:
    if reference:
        _profile_cache[reference] = profile
        if len(_profile_cache) > CACHE_MAX_ENTRIES:
            keys = list(_profile_cache.keys())[: len(_profile_cache) - CACHE_MAX_ENTRIES]
            for key in keys:
                _profile_cache.pop(key, None)

    fp = fingerprint or (reference and _ref_fingerprints.get(reference))
    if fp:
        remember_fingerprint(reference, fp)
        try:
            get_analysis_cache().put(KIND_PROFILE, fp, profile)
        except Exception as exc:
            logger.debug("Durable profile put failed", extra={"error": str(exc)})


def get_forecast(
    reference: str | None,
    target: str,
    *,
    fingerprint: str | None = None,
    horizon: int | None = None,
    time_col: str | None = None,
) -> dict[str, Any] | None:
    ram_key = f"{reference}:{target}" if reference else None
    if ram_key and ram_key in _forecast_cache:
        return _forecast_cache.get(ram_key)

    fp = fingerprint or (reference and _ref_fingerprints.get(reference))
    if fp:
        params: dict[str, Any] = {"target": target}
        if horizon is not None:
            params["horizon"] = horizon
        if time_col:
            params["time_col"] = time_col
        try:
            payload = get_analysis_cache().get(KIND_FORECAST, fp, params)
            if isinstance(payload, dict):
                if ram_key:
                    _forecast_cache[ram_key] = payload
                return payload
        except Exception as exc:
            logger.debug("Durable forecast get failed", extra={"error": str(exc)})
    return None


def set_forecast(
    reference: str | None,
    target: str,
    forecast: list[dict[str, Any]],
    chart: Any,
    *,
    fingerprint: str | None = None,
    horizon: int | None = None,
    time_col: str | None = None,
) -> None:
    payload = {
        "forecast": forecast,
        "forecast_chart": chart,
    }
    ram_key = f"{reference}:{target}" if reference else None
    if ram_key:
        _forecast_cache[ram_key] = payload
        if len(_forecast_cache) > CACHE_MAX_ENTRIES:
            keys = list(_forecast_cache.keys())[: len(_forecast_cache) - CACHE_MAX_ENTRIES]
            for key in keys:
                _forecast_cache.pop(key, None)

    fp = fingerprint or (reference and _ref_fingerprints.get(reference))
    if fp:
        remember_fingerprint(reference, fp)
        params: dict[str, Any] = {"target": target}
        if horizon is not None:
            params["horizon"] = horizon
        if time_col:
            params["time_col"] = time_col
        try:
            get_analysis_cache().put(KIND_FORECAST, fp, payload, params)
        except Exception as exc:
            logger.debug("Durable forecast put failed", extra={"error": str(exc)})


def get_embeddings(
    reference: str | None = None,
    *,
    fingerprint: str | None = None,
    model: str | None = None,
) -> Any:
    if reference and reference in _embedding_cache:
        return _embedding_cache.get(reference)

    fp = fingerprint or (reference and _ref_fingerprints.get(reference))
    if fp:
        params = {"model": model or "default"}
        try:
            payload = get_analysis_cache().get(KIND_EMBEDDING, fp, params)
            if payload is not None:
                if reference:
                    _embedding_cache[reference] = payload
                return payload
        except Exception as exc:
            logger.debug("Durable embedding get failed", extra={"error": str(exc)})
    return None


def set_embeddings(
    reference: str | None,
    embeddings: Any,
    *,
    fingerprint: str | None = None,
    model: str | None = None,
) -> None:
    if reference:
        _embedding_cache[reference] = embeddings
        if len(_embedding_cache) > CACHE_MAX_ENTRIES:
            keys = list(_embedding_cache.keys())[: len(_embedding_cache) - CACHE_MAX_ENTRIES]
            for key in keys:
                _embedding_cache.pop(key, None)

    fp = fingerprint or (reference and _ref_fingerprints.get(reference))
    if fp:
        remember_fingerprint(reference, fp)
        params = {"model": model or "default"}
        try:
            get_analysis_cache().put(KIND_EMBEDDING, fp, embeddings, params)
        except Exception as exc:
            logger.debug("Durable embedding put failed", extra={"error": str(exc)})
