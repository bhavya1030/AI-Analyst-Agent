from collections import OrderedDict
from typing import Any

import pandas as pd

CACHE_MAX_ENTRIES = 64

_dataset_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
_profile_cache: dict[str, dict[str, Any]] = {}
_forecast_cache: dict[str, dict[str, Any]] = {}
_embedding_cache: dict[str, Any] = {}


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


def get_profile(reference: str) -> dict[str, Any] | None:
    return _profile_cache.get(reference)


def set_profile(reference: str, profile: dict[str, Any]) -> None:
    _profile_cache[reference] = profile
    if len(_profile_cache) > CACHE_MAX_ENTRIES:
        keys = list(_profile_cache.keys())[: len(_profile_cache) - CACHE_MAX_ENTRIES]
        for key in keys:
            _profile_cache.pop(key, None)


def get_forecast(reference: str, target: str) -> dict[str, Any] | None:
    return _forecast_cache.get(f"{reference}:{target}")


def set_forecast(reference: str, target: str, forecast: list[dict[str, Any]], chart: Any) -> None:
    _forecast_cache[f"{reference}:{target}"] = {
        "forecast": forecast,
        "forecast_chart": chart,
    }
    if len(_forecast_cache) > CACHE_MAX_ENTRIES:
        keys = list(_forecast_cache.keys())[: len(_forecast_cache) - CACHE_MAX_ENTRIES]
        for key in keys:
            _forecast_cache.pop(key, None)


def get_embeddings(reference: str) -> Any:
    return _embedding_cache.get(reference)


def set_embeddings(reference: str, embeddings: Any) -> None:
    _embedding_cache[reference] = embeddings
    if len(_embedding_cache) > CACHE_MAX_ENTRIES:
        keys = list(_embedding_cache.keys())[: len(_embedding_cache) - CACHE_MAX_ENTRIES]
        for key in keys:
            _embedding_cache.pop(key, None)
