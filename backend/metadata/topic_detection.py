"""Topic detection from questions, filenames, columns, and sample values.

Used by metadata generation and the dataset topic agent so uploads no longer
collapse to "user provided dataset".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Sequence

from backend.metadata.models import is_placeholder_label

# Metric phrases (longest first) → display label
METRIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgross\s+domestic\s+product\b", re.I), "GDP"),
    (re.compile(r"\bgdp\b", re.I), "GDP"),
    (re.compile(r"\binflation\b|\bcpi\b|consumer\s+price", re.I), "Inflation"),
    (re.compile(r"\bpopulation\b", re.I), "Population"),
    (re.compile(r"\bunemployment\b|jobless", re.I), "Unemployment"),
    (re.compile(r"\bco2\b|carbon\s+dioxide|emissions?\b", re.I), "CO2 Emissions"),
    (re.compile(r"\btemperature\b|climate\b|rainfall\b|precipitation\b", re.I), "Climate"),
    (re.compile(r"\bgold(\s+price|\s+rate)?\b", re.I), "Gold Price"),
    (re.compile(r"\boil(\s+price)?\b", re.I), "Oil Price"),
    (re.compile(r"\bstock\b|s\s*&\s*p|equity\b", re.I), "Stock Market"),
    (re.compile(r"\bcovid\b|coronavirus\b", re.I), "COVID-19"),
    (re.compile(r"\brevenue\b|\bsales\b|\bprofit\b", re.I), "Sales"),
    (re.compile(r"\benergy\b|\belectricity\b|\brenewable\b", re.I), "Energy"),
    (re.compile(r"\bhappiness\b|\bwellbeing\b", re.I), "Happiness"),
    (re.compile(r"\bair\s+quality\b|\bpm2\.?5\b|\baqi\b", re.I), "Air Quality"),
]

COUNTRY_CANONICAL: dict[str, str] = {
    "india": "India",
    "china": "China",
    "usa": "United States",
    "us": "United States",
    "united states": "United States",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "japan": "Japan",
    "germany": "Germany",
    "france": "France",
    "brazil": "Brazil",
    "canada": "Canada",
    "australia": "Australia",
    "mexico": "Mexico",
    "russia": "Russia",
    "indonesia": "Indonesia",
    "italy": "Italy",
    "spain": "Spain",
    "korea": "South Korea",
    "south korea": "South Korea",
    "turkey": "Turkey",
    "saudi arabia": "Saudi Arabia",
    "south africa": "South Africa",
    "nigeria": "Nigeria",
    "pakistan": "Pakistan",
    "bangladesh": "Bangladesh",
    "ethiopia": "Ethiopia",
}

_STRIP_PATTERN = re.compile(
    r"\b("
    r"analyze|analyse|analysis|study|explore|investigate|show|plot|chart|graph|"
    r"forecast|predict|compare|visualize|visualise|display|summarize|summarise|"
    r"summary|find|fetch|download|get|search|dataset|data|about|on|of|the|a|an|"
    r"for|next|previous|past|last|coming|upcoming|please|help|me|with|using|"
    r"over|across|deeply|trend|trends|rate|rates|price|prices|history|historical|"
    r"growth|and|to|from|years?|months?|days?|csv|json|file|upload"
    r")\b",
    re.IGNORECASE,
)

_TOPIC_KEEP = {
    "gold", "silver", "oil", "bitcoin", "crypto", "stock", "gdp", "inflation",
    "population", "covid", "climate", "temperature", "unemployment", "energy",
}


def detect_metrics_from_text(text: str) -> list[str]:
    found: list[str] = []
    for pattern, label in METRIC_PATTERNS:
        if pattern.search(text or ""):
            if label not in found:
                found.append(label)
    return found


def detect_metrics_from_columns(columns: Sequence[str]) -> list[str]:
    return detect_metrics_from_text(" ".join(str(c) for c in columns))


def detect_countries_from_text(text: str) -> list[str]:
    t = (text or "").lower()
    found: list[str] = []
    for key in sorted(COUNTRY_CANONICAL.keys(), key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", t):
            label = COUNTRY_CANONICAL[key]
            if label not in found:
                found.append(label)
    return found


def detect_countries_from_values(values: Sequence[Any], *, limit: int = 12) -> list[str]:
    """Map sample cell values to canonical country names."""
    found: list[str] = []
    for raw in values:
        if raw is None:
            continue
        s = str(raw).strip()
        if not s or len(s) > 64:
            continue
        low = s.lower()
        if low in COUNTRY_CANONICAL:
            label = COUNTRY_CANONICAL[low]
            if label not in found:
                found.append(label)
            continue
        for key, label in COUNTRY_CANONICAL.items():
            if key in low or low in key:
                if label not in found:
                    found.append(label)
                break
        if len(found) >= limit:
            break
    return found[:limit]


def topic_from_filename(path: str | Path | None) -> str:
    if not path:
        return ""
    stem = Path(str(path)).stem
    # Drop common noise suffixes
    stem = re.sub(r"(_?\d{6,}|_?v\d+|copy|final|data|dataset)$", "", stem, flags=re.I)
    stem = stem.replace("_", " ").replace("-", " ").replace(".", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    if not stem or stem.lower() in {"data", "dataset", "upload", "file", "tmp"}:
        return ""
    # Title-case known tokens
    countries = detect_countries_from_text(stem)
    metrics = detect_metrics_from_text(stem)
    if countries or metrics:
        return compose_topic(countries, metrics, residual=_residual_words(stem, countries, metrics))
    return _title_case_phrase(stem)


def topic_from_question(question: str | None) -> str:
    if not question:
        return ""
    normalized = question.lower()
    kept = [tok for tok in _TOPIC_KEEP if re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", normalized)]
    cleaned = _STRIP_PATTERN.sub(" ", normalized)
    cleaned = re.sub(r"\b\d+\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if kept:
        residual = [w for w in cleaned.split() if w not in kept]
        cleaned = " ".join(kept + residual).strip()

    countries = detect_countries_from_text(normalized)
    metrics = detect_metrics_from_text(normalized)
    free = cleaned if cleaned not in {"", "data", "dataset", "it", "this", "that"} else ""
    free_tokens = free.split() if free else []

    covered: set[str] = set()
    for c in countries:
        covered.update(c.lower().split())
    for m in metrics:
        covered.update(m.lower().split())
    covered.update({"united", "states", "kingdom", "south", "korea", "saudi", "arabia", "africa"})
    residual = [t for t in free_tokens if t not in covered]

    if metrics and not residual and len(free_tokens) <= 6:
        return compose_topic(countries, metrics, residual=[])
    if free:
        return _title_case_phrase(free)
    if metrics or countries:
        return compose_topic(countries, metrics, residual=[])
    return ""


def topic_from_columns_and_values(
    columns: Sequence[str],
    *,
    sample_values: Sequence[Any] | None = None,
    filename: str | None = None,
    question: str | None = None,
) -> str:
    """Build a display topic like 'India GDP' from structure + context."""
    # Prefer explicit user question when it yields a real topic
    q_topic = topic_from_question(question)
    if q_topic and not is_placeholder_label(q_topic):
        return q_topic

    file_topic = topic_from_filename(filename)
    col_blob = " ".join(str(c) for c in columns)
    file_blob = Path(str(filename)).stem if filename else ""
    countries = detect_countries_from_text(f"{file_blob} {col_blob}")
    if sample_values:
        for c in detect_countries_from_values(sample_values):
            if c not in countries:
                countries.append(c)
    metrics = detect_metrics_from_text(f"{file_blob} {col_blob}")
    if not metrics:
        # Column names themselves as soft metrics (GDP, Value, Price)
        for col in columns:
            m = detect_metrics_from_text(str(col))
            for item in m:
                if item not in metrics:
                    metrics.append(item)

    if countries or metrics:
        residual = _residual_words(
            f"{file_blob} {col_blob}".replace("_", " "),
            countries,
            metrics,
        )
        composed = compose_topic(countries, metrics, residual=residual[:3])
        if composed and not is_placeholder_label(composed):
            return composed

    if file_topic and not is_placeholder_label(file_topic):
        return file_topic

    # Last resort: humanize primary metric-like column
    for col in columns:
        cl = str(col).lower()
        if cl in {"country", "year", "date", "id", "code", "name", "region", "index"}:
            continue
        return _title_case_phrase(str(col).replace("_", " "))

    return "Tabular Dataset"


def compose_topic(
    countries: Sequence[str],
    metrics: Sequence[str],
    *,
    residual: Sequence[str] | None = None,
) -> str:
    parts: list[str] = []
    for c in countries[:2]:
        if c and c not in parts:
            parts.append(c)
    for m in metrics[:2]:
        if m and m not in parts:
            parts.append(m)
    for r in residual or []:
        rr = _title_case_phrase(r)
        if rr and rr.lower() not in {p.lower() for p in parts}:
            parts.append(rr)
    return " ".join(parts).strip()


def _residual_words(
    text: str,
    countries: Sequence[str],
    metrics: Sequence[str],
) -> list[str]:
    covered: set[str] = set()
    for c in countries:
        covered.update(c.lower().split())
    for m in metrics:
        covered.update(re.findall(r"[a-z0-9]+", m.lower()))
    covered.update(
        {
            "united", "states", "kingdom", "south", "korea", "saudi", "arabia",
            "africa", "name", "code", "value", "data", "dataset", "csv", "json",
        }
    )
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text or "")
    out: list[str] = []
    for w in words:
        if w.lower() in covered:
            continue
        if w.lower() not in {o.lower() for o in out}:
            out.append(w)
    return out[:4]


def _title_case_phrase(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    if not words:
        return ""
    # Keep known acronyms upper
    acronyms = {"gdp", "cpi", "co2", "ev", "api", "usa", "uk", "pm25", "aqi"}
    out = []
    for w in words:
        if w.lower() in acronyms:
            out.append(w.upper() if w.lower() != "co2" else "CO2")
        else:
            out.append(w.capitalize())
    return " ".join(out)


def prefer_non_placeholder(*candidates: Optional[str]) -> str:
    for c in candidates:
        if c and not is_placeholder_label(c):
            return str(c).strip()
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip()
    return "Tabular Dataset"
