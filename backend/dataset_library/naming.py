"""Safe, deterministic path segment generation for library folders."""

from __future__ import annotations

import re
import unicodedata


_UNSAFE = re.compile(r"[^a-z0-9._-]+")
_MULTI_SEP = re.compile(r"[-_.]{2,}")


def slugify(value: str | None, *, fallback: str = "unknown", max_length: int = 64) -> str:
    """Turn arbitrary labels into filesystem-safe folder names.

    Examples:
        "World Bank" -> "world_bank"
        "India GDP!!" -> "india_gdp"
    """
    text = (value or "").strip()
    if not text:
        return fallback

    # Normalize unicode → ascii-ish
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
    text = _UNSAFE.sub("_", text)
    text = _MULTI_SEP.sub("_", text)
    text = text.strip("._-")

    if not text:
        return fallback
    if len(text) > max_length:
        text = text[:max_length].rstrip("._-")
    return text or fallback


def dataset_relative_dir(source: str | None, topic: str | None, dataset_id: str) -> str:
    """Relative directory for a dataset (posix-style segments).

    Layout:
        {source_slug}/{topic_slug}/{dataset_id}/
    """
    source_slug = slugify(source, fallback="unknown_source")
    topic_slug = slugify(topic, fallback="unknown_topic")
    id_slug = slugify(dataset_id, fallback="unknown_id", max_length=80)
    return f"{source_slug}/{topic_slug}/{id_slug}"
