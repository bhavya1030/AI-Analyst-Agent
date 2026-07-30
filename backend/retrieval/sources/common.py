"""Shared helpers for open-data source connectors."""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

import requests

from backend.core.logger import get_logger

logger = get_logger(__name__)

REQUEST_TIMEOUT = 8
USER_AGENT = "AI-Analyst-Agent/1.0 (dataset-retrieval)"

LOADABLE_EXTENSIONS = (".csv", ".json", ".xlsx", ".xls", ".parquet")


def topic_tokens(topic: str) -> list[str]:
    stop = {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by",
        "data", "dataset", "datasets", "open", "csv", "json", "analyze", "study",
    }
    return [
        t
        for t in re.findall(r"[a-z0-9]+", (topic or "").lower())
        if len(t) > 2 and t not in stop
    ]


def is_loadable_url(url: str | None) -> bool:
    if not url:
        return False
    lower_full = url.lower()
    # Never treat HTML search / wiki / login pages as loadable datasets
    if any(
        bad in lower_full
        for bad in (
            "/searchresults",
            "wikipedia.org",
            "/login",
            "/signin",
            "/w/index.php",
        )
    ):
        return False
    lower = lower_full.split("?")[0]
    if any(lower.endswith(ext) for ext in LOADABLE_EXTENSIONS):
        return True
    # Structured JSON APIs that return datasets (not HTML)
    if "api.worldbank.org" in lower_full and "format=json" in lower_full:
        return True
    if "api.coingecko.com" in lower_full:
        return True
    if "raw.githubusercontent.com" in lower_full:
        return True
    if "/sdmx-json/data/" in lower_full:
        return True
    return False


def guess_format(url: str | None) -> str:
    if not url:
        return "unknown"
    lower = url.lower().split("?")[0]
    for ext in LOADABLE_EXTENSIONS:
        if lower.endswith(ext):
            return ext.lstrip(".")
    return "unknown"


def http_get_json(url: str, *, params: dict | None = None, timeout: int = REQUEST_TIMEOUT):
    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        if response.status_code != 200:
            return None
        return response.json()
    except Exception as exc:
        logger.warning("Source HTTP GET failed", extra={"url": url, "error": str(exc)})
        return None


def score_text(topic: str, *parts: str) -> int:
    tokens = topic_tokens(topic)
    blob = " ".join(p or "" for p in parts).lower()
    if not tokens or not blob:
        return 0
    score = 0
    topic_l = (topic or "").lower()
    if topic_l and topic_l in blob:
        score += 10
    for tok in tokens:
        if tok in blob:
            score += 2
    return score


def prefer_loadable(candidates: Iterable[dict]) -> list[dict]:
    items = list(candidates)
    items.sort(
        key=lambda c: (
            1 if is_loadable_url(c.get("download_url") or c.get("url")) else 0,
            int(c.get("rank_hint") or 0),
        ),
        reverse=True,
    )
    return items


def host_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""
