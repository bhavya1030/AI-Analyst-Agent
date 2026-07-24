"""Duplicate detection for Dataset Learning Service."""

from __future__ import annotations

from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.learning.models import LearningInput
from backend.registry.models import DatasetMetadata


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Drop volatile query params
        drop = {"utm_source", "utm_medium", "utm_campaign", "download"}
        qs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in drop]
        clean = parsed._replace(
            scheme=(parsed.scheme or "https").lower(),
            netloc=parsed.netloc.lower(),
            path=parsed.path.rstrip("/") or parsed.path,
            query=urlencode(qs),
            fragment="",
        )
        return urlunparse(clean)
    except Exception:
        return (url or "").strip().lower()


def normalize_title(title: str | None) -> str:
    return " ".join((title or "").strip().lower().split())


def normalize_source(source: str | None) -> str:
    return (source or "").strip().lower()


def find_duplicate(
    candidates: list[DatasetMetadata],
    incoming: LearningInput,
) -> Optional[DatasetMetadata]:
    """
    Identify an existing registry row for the same physical/logical dataset.

    Priority:
      1. exact dataset_id
      2. exact checksum (strongest content identity)
      3. normalized download_url
      4. title + source (weaker; same publisher listing)
    """
    if not candidates:
        return None

    if incoming.dataset_id:
        for c in candidates:
            if c.dataset_id == incoming.dataset_id:
                return c

    if incoming.checksum:
        ck = incoming.checksum.strip().lower()
        for c in candidates:
            if (c.checksum or "").strip().lower() == ck and ck:
                return c

    url = normalize_url(incoming.download_url)
    if url:
        for c in candidates:
            if normalize_url(c.download_url) == url:
                return c

    title = normalize_title(incoming.title)
    source = normalize_source(incoming.source)
    if title and source:
        for c in candidates:
            if normalize_title(c.title) == title and normalize_source(c.source) == source:
                return c

    return None
