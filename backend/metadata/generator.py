"""Automatic dataset metadata generation from columns, stats, and optional LLM."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

from backend.core.logger import get_logger
from backend.metadata.models import GeneratedDatasetMetadata, is_placeholder_label
from backend.metadata.topic_detection import (
    detect_countries_from_text,
    detect_countries_from_values,
    detect_metrics_from_columns,
    detect_metrics_from_text,
    prefer_non_placeholder,
    topic_from_columns_and_values,
    topic_from_filename,
    topic_from_question,
)

logger = get_logger(__name__)

_SAMPLE_ROWS = 200

# Lightweight domain lexicon (aligned with intelligence / registry)
_DOMAIN_LEXICON: dict[str, set[str]] = {
    "economics": {"gdp", "inflation", "cpi", "unemployment", "trade", "export", "import", "economy", "income"},
    "finance": {"price", "stock", "equity", "bond", "fx", "interest", "gold", "silver", "oil", "revenue", "profit"},
    "demographics": {"population", "birth", "death", "age", "gender", "migration"},
    "health": {"disease", "hospital", "mortality", "covid", "vaccine", "health", "cases"},
    "energy": {"energy", "electricity", "power", "coal", "gas", "renewable", "emission", "co2"},
    "climate": {"temperature", "rainfall", "precipitation", "humidity", "climate", "weather"},
    "education": {"school", "student", "literacy", "education", "enrollment"},
}

_TIME_TOKENS = {"date", "time", "datetime", "timestamp", "year", "month", "day", "period", "week"}
_ENTITY_TOKENS = {
    "country", "nation", "region", "state", "city", "entity", "name", "location",
    "iso", "symbol", "ticker",
}


def generate_metadata(
    *,
    df: pd.DataFrame | None = None,
    local_path: str | Path | None = None,
    columns: Sequence[str] | None = None,
    question: str | None = None,
    hint_topic: str | None = None,
    source: str = "",
    source_type: str = "Other",
    download_url: str | None = None,
    use_llm: bool = False,
    profile: dict[str, Any] | None = None,
) -> GeneratedDatasetMetadata:
    """
    Generate rich metadata for a dataset.

    Uses column names, lightweight statistics (sample), filename, optional
    structural profile, and optional LLM refinement.
    """
    path = Path(local_path).expanduser() if local_path else None
    frame = df
    if frame is None and path is not None and path.is_file():
        frame = _read_sample(path)

    col_names = [str(c) for c in (columns or (list(frame.columns) if frame is not None else []))]
    stats = _compute_column_stats(frame) if frame is not None else {}
    sample_entity_values = _sample_entity_values(frame, col_names)

    # Structural fields
    time_column = (profile or {}).get("time_column") or _detect_time_column(frame, col_names)
    primary_entity = (
        (profile or {}).get("entity_column")
        or (profile or {}).get("primary_entity")
        or _detect_entity_column(frame, col_names, time_column)
    )
    metrics = list((profile or {}).get("numeric_metrics") or (profile or {}).get("metrics") or [])
    if not metrics and frame is not None:
        metrics = _numeric_metric_columns(frame, time_column)
    if not metrics:
        metrics = [c for c in detect_metrics_from_columns(col_names)]

    countries = list((profile or {}).get("countries_regions") or (profile or {}).get("country") or [])
    if not countries:
        countries = detect_countries_from_text(
            " ".join(
                [
                    str(path.stem if path else ""),
                    " ".join(col_names),
                    hint_topic or "",
                    question or "",
                ]
            )
        )
        for c in detect_countries_from_values(sample_entity_values):
            if c not in countries:
                countries.append(c)

    domain = (
        (profile or {}).get("domain")
        or _detect_domain(col_names, metrics, path.stem if path else "", hint_topic or "", question or "")
    )

    keywords = _build_keywords(col_names, countries, metrics, path.stem if path else "", domain)
    tags = _build_tags(domain, countries, metrics, keywords, source_type)

    title = _build_title(
        columns=col_names,
        countries=countries,
        metrics=metrics,
        filename=str(path) if path else None,
        question=question,
        hint_topic=hint_topic,
        primary_entity=primary_entity,
    )
    topic = prefer_non_placeholder(
        title if not is_placeholder_label(title) else None,
        topic_from_question(question),
        topic_from_filename(path) if path else None,
        hint_topic if not is_placeholder_label(hint_topic) else None,
        title,
    )

    date_range = (profile or {}).get("date_range") or _date_range(frame, time_column)
    row_count = (profile or {}).get("row_count")
    if row_count is None and frame is not None:
        row_count = int(frame.attrs.get("row_count_estimate") or len(frame))

    description = _build_description(
        title=title,
        domain=domain,
        countries=countries,
        metrics=metrics,
        time_column=time_column,
        primary_entity=primary_entity,
        columns=col_names,
        row_count=row_count,
        date_range=date_range,
        stats=stats,
    )
    summary = _build_summary(
        title=title,
        domain=domain,
        countries=countries,
        metrics=metrics,
        row_count=row_count,
        date_range=date_range,
        time_column=time_column,
        primary_entity=primary_entity,
    )

    file_format = (
        (profile or {}).get("file_format")
        or (path.suffix.lstrip(".").lower() if path else "unknown")
        or "unknown"
    )
    dataset_type = (profile or {}).get("dataset_type") or (
        "time_series" if time_column and metrics else ("tabular" if col_names else "unknown")
    )
    checksum = None
    if path is not None and path.is_file():
        checksum = _file_checksum(path)

    meta = GeneratedDatasetMetadata(
        title=title,
        description=description,
        domain=domain or "general",
        country=countries[:20],
        metrics=[str(m) for m in metrics[:30]],
        time_column=time_column,
        primary_entity=primary_entity,
        tags=tags[:40],
        keywords=keywords[:40],
        summary=summary,
        topic=topic,
        columns=col_names,
        row_count=int(row_count) if row_count is not None else None,
        date_range=date_range if isinstance(date_range, dict) else None,
        dataset_type=str(dataset_type),
        file_format=str(file_format or "unknown"),
        local_path=str(path.resolve()) if path and path.is_file() else (str(path) if path else None),
        download_url=download_url,
        source=source or "",
        source_type=source_type or "Other",
        checksum=checksum,
        generator="rule_based",
        notes=[],
    )

    if use_llm:
        meta = _maybe_llm_enrich(meta, stats=stats, question=question)

    logger.info(
        "Generated dataset metadata",
        extra={
            "title": meta.title,
            "topic": meta.topic,
            "domain": meta.domain,
            "countries": meta.country[:5],
            "metrics": meta.metrics[:5],
            "generator": meta.generator,
        },
    )
    return meta


def _build_title(
    *,
    columns: Sequence[str],
    countries: Sequence[str],
    metrics: Sequence[str],
    filename: str | None,
    question: str | None,
    hint_topic: str | None,
    primary_entity: str | None,
) -> str:
    # Structured compose from countries + metrics (e.g. India + GDP → "India GDP")
    composed = topic_from_columns_and_values(
        columns,
        sample_values=None,
        filename=filename,
        question=question,
    )
    # Re-compose using already-detected country/metric lists for consistency
    if countries or metrics:
        from backend.metadata.topic_detection import compose_topic

        metric_labels = []
        for m in metrics:
            # Prefer human labels for known metrics in column names
            labels = detect_metrics_from_text(str(m))
            if labels:
                metric_labels.extend(labels)
            elif not re.match(r"^(value|amount|number|count)$", str(m), re.I):
                # Keep column name if it's a real metric label
                if detect_metrics_from_text(str(m)) or any(
                    k in str(m).lower() for k in ("gdp", "price", "rate", "population", "inflation", "co2")
                ):
                    metric_labels.append(str(m).replace("_", " ").strip())
        # If metrics are raw columns like "GDP", use them as labels
        if not metric_labels:
            for m in metrics[:3]:
                ml = str(m).replace("_", " ").strip()
                if ml.lower() not in {"value", "amount", "number", "count", "id"}:
                    # Title-ish
                    metric_labels.append(ml if ml.isupper() or len(ml) <= 4 else ml.title())
        # Normalize GDP-like
        normalized_metrics = []
        for m in metric_labels or list(metrics)[:2]:
            labels = detect_metrics_from_text(str(m))
            if labels:
                for lb in labels:
                    if lb not in normalized_metrics:
                        normalized_metrics.append(lb)
            else:
                sm = str(m).replace("_", " ").strip()
                if sm and sm not in normalized_metrics:
                    normalized_metrics.append(sm if len(sm) <= 6 and sm.isupper() else sm.title())
        title = compose_topic(list(countries)[:2], normalized_metrics[:2])
        if title and not is_placeholder_label(title):
            return title

    if composed and not is_placeholder_label(composed):
        return composed

    if hint_topic and not is_placeholder_label(hint_topic):
        return str(hint_topic).strip().title() if hint_topic.islower() else str(hint_topic).strip()

    file_t = topic_from_filename(filename)
    if file_t:
        return file_t

    if primary_entity and metrics:
        return f"{primary_entity.replace('_', ' ').title()} Metrics"

    return "Tabular Dataset"


def _build_description(
    *,
    title: str,
    domain: str,
    countries: Sequence[str],
    metrics: Sequence[str],
    time_column: str | None,
    primary_entity: str | None,
    columns: Sequence[str],
    row_count: int | None,
    date_range: dict | None,
    stats: dict[str, Any],
) -> str:
    bits: list[str] = [f"{title} dataset"]
    if domain and domain != "general":
        bits.append(f"in the {domain} domain")
    if countries:
        bits.append("covering " + ", ".join(countries[:5]))
    if metrics:
        metric_names = [str(m) for m in metrics[:6]]
        bits.append("with metrics " + ", ".join(metric_names))
    if primary_entity:
        bits.append(f"(entity: {primary_entity})")
    if time_column:
        bits.append(f"indexed by {time_column}")
    if date_range and date_range.get("start") and date_range.get("end"):
        bits.append(f"from {date_range['start']} to {date_range['end']}")
    if row_count:
        bits.append(f"— {row_count:,} rows, {len(columns)} columns")
    # Light stats hint
    for m in list(metrics)[:2]:
        st = stats.get(str(m))
        if st and st.get("min") is not None and st.get("max") is not None:
            bits.append(f"{m} range {st['min']}–{st['max']}")
            break
    text = " ".join(bits).strip()
    if not text.endswith("."):
        text += "."
    return text


def _build_summary(
    *,
    title: str,
    domain: str,
    countries: Sequence[str],
    metrics: Sequence[str],
    row_count: int | None,
    date_range: dict | None,
    time_column: str | None,
    primary_entity: str | None,
) -> str:
    parts = [title]
    if countries:
        parts.append("Countries: " + ", ".join(countries[:8]))
    if metrics:
        parts.append("Metrics: " + ", ".join(str(m) for m in metrics[:8]))
    if domain and domain != "general":
        parts.append(f"Domain: {domain}")
    if time_column:
        parts.append(f"Time column: {time_column}")
    if primary_entity:
        parts.append(f"Primary entity: {primary_entity}")
    if date_range and date_range.get("start"):
        parts.append(f"Range: {date_range.get('start')} → {date_range.get('end')}")
    if row_count is not None:
        parts.append(f"Rows: {row_count}")
    return " | ".join(parts)


def _build_keywords(
    columns: Sequence[str],
    countries: Sequence[str],
    metrics: Sequence[str],
    stem: str,
    domain: str,
) -> list[str]:
    words: list[str] = []
    blob = " ".join(list(columns) + list(metrics) + [stem, domain] + list(countries))
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", blob.lower()):
        if token in {"the", "and", "for", "data", "dataset", "unnamed", "column", "value"}:
            continue
        if token not in words:
            words.append(token)
    for c in countries:
        for part in c.lower().split():
            if part not in words and len(part) > 2:
                words.append(part)
    return words[:25]


def _build_tags(
    domain: str,
    countries: Sequence[str],
    metrics: Sequence[str],
    keywords: Sequence[str],
    source_type: str,
) -> list[str]:
    tags: list[str] = []
    if domain and domain != "general":
        tags.append(domain)
    for c in countries[:5]:
        if c not in tags:
            tags.append(c)
    for m in metrics[:8]:
        label = str(m)
        if label not in tags:
            tags.append(label)
    if source_type and source_type not in tags:
        tags.append(source_type)
    for kw in keywords:
        if kw not in tags and len(tags) < 25:
            tags.append(kw)
    return tags


def _detect_domain(
    columns: Sequence[str],
    metrics: Sequence[str],
    stem: str,
    hint: str,
    question: str,
) -> str:
    blob = " ".join(
        [str(c) for c in columns]
        + [str(m) for m in metrics]
        + [stem, hint or "", question or ""]
    ).lower()
    tokens = set(re.findall(r"[a-z0-9]+", blob))
    best = "general"
    best_hits = 0
    for domain, lexicon in _DOMAIN_LEXICON.items():
        hits = len(tokens & lexicon)
        # also substring hits
        for key in lexicon:
            if key in blob:
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best = domain
    return best if best_hits else "general"


def _detect_time_column(df: pd.DataFrame | None, columns: Sequence[str]) -> Optional[str]:
    for col in columns:
        tokens = set(re.findall(r"[a-z0-9]+", str(col).lower()))
        if tokens & _TIME_TOKENS:
            return str(col)
    if df is None:
        return None
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return str(col)
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            vals = pd.to_numeric(series, errors="coerce").dropna()
            if len(vals) >= 3 and vals.between(1800, 2100).mean() >= 0.9 and vals.nunique() >= 3:
                return str(col)
    return None


def _detect_entity_column(
    df: pd.DataFrame | None,
    columns: Sequence[str],
    time_column: str | None,
) -> Optional[str]:
    for col in columns:
        if time_column and str(col) == str(time_column):
            continue
        tokens = set(re.findall(r"[a-z0-9]+", str(col).lower()))
        if tokens & _ENTITY_TOKENS:
            return str(col)
    if df is None:
        return None
    best = None
    best_score = -1
    for col in df.columns:
        name = str(col)
        if time_column and name == time_column:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        score = 0
        tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
        if tokens & _ENTITY_TOKENS:
            score += 5
        nunique = df[col].nunique(dropna=True)
        n = max(1, len(df))
        if 1 < nunique <= max(3, int(0.5 * n)):
            score += 2
        if score > best_score:
            best_score = score
            best = name
    return best if best_score > 0 else None


def _numeric_metric_columns(df: pd.DataFrame, time_column: str | None) -> list[str]:
    out: list[str] = []
    for col in df.columns:
        name = str(col)
        if time_column and name == time_column:
            continue
        tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
        if tokens & _ENTITY_TOKENS:
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
            out.append(name)
        else:
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.notna().mean() >= 0.8:
                out.append(name)
    return out


def _sample_entity_values(df: pd.DataFrame | None, columns: Sequence[str]) -> list[Any]:
    if df is None or df.empty:
        return []
    values: list[Any] = []
    preferred = [
        c
        for c in columns
        if set(re.findall(r"[a-z0-9]+", str(c).lower())) & _ENTITY_TOKENS
    ]
    for col in (preferred or list(columns))[:3]:
        if col not in df.columns:
            continue
        for v in df[col].dropna().astype(str).head(40).tolist():
            values.append(v)
    return values


def _compute_column_stats(df: pd.DataFrame) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            s = pd.to_numeric(series, errors="coerce").dropna()
            if s.empty:
                continue
            stats[str(col)] = {
                "min": float(s.min()),
                "max": float(s.max()),
                "mean": float(s.mean()),
                "null_pct": float(series.isna().mean()),
            }
        else:
            stats[str(col)] = {
                "nunique": int(series.nunique(dropna=True)),
                "null_pct": float(series.isna().mean()),
                "sample": [str(v) for v in series.dropna().head(3).tolist()],
            }
    return stats


def _date_range(df: pd.DataFrame | None, time_column: str | None) -> Optional[dict[str, Any]]:
    if df is None or not time_column or time_column not in df.columns:
        return None
    series = df[time_column]
    try:
        if pd.api.types.is_numeric_dtype(series):
            vals = pd.to_numeric(series, errors="coerce").dropna()
            if vals.empty:
                return None
            if vals.between(1800, 2100).mean() >= 0.8:
                return {"start": str(int(vals.min())), "end": str(int(vals.max()))}
        parsed = pd.to_datetime(series, errors="coerce").dropna()
        if parsed.empty:
            return None
        return {"start": str(parsed.min().date()), "end": str(parsed.max().date())}
    except Exception:
        return None


def _read_sample(path: Path) -> pd.DataFrame:
    fmt = path.suffix.lower().lstrip(".")
    if fmt == "csv":
        df = pd.read_csv(path, nrows=_SAMPLE_ROWS)
        try:
            with path.open("rb") as f:
                row_count = max(0, sum(1 for _ in f) - 1)
            df.attrs["row_count_estimate"] = row_count
        except Exception:
            df.attrs["row_count_estimate"] = len(df)
        return df
    if fmt == "json":
        try:
            df = pd.read_json(path)
        except Exception:
            df = pd.read_json(path, lines=True)
        df.attrs["row_count_estimate"] = len(df)
        return df.head(_SAMPLE_ROWS)
    if fmt in {"xlsx", "xls"}:
        df = pd.read_excel(path, nrows=_SAMPLE_ROWS)
        df.attrs["row_count_estimate"] = len(df)
        return df
    if fmt == "parquet":
        df = pd.read_parquet(path)
        df.attrs["row_count_estimate"] = len(df)
        return df.head(_SAMPLE_ROWS)
    df = pd.read_csv(path, nrows=_SAMPLE_ROWS)
    df.attrs["row_count_estimate"] = len(df)
    return df


def _file_checksum(path: Path, *, max_bytes: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
            if total >= max_bytes:
                return f"partial:{h.hexdigest()}"
    return h.hexdigest()


def _maybe_llm_enrich(
    meta: GeneratedDatasetMetadata,
    *,
    stats: dict[str, Any],
    question: str | None,
) -> GeneratedDatasetMetadata:
    """Optional Ollama refinement for title/description/summary."""
    try:
        from backend.config import settings
        from backend.llm.ollama_client import invoke_llm
    except Exception as exc:
        meta.notes.append(f"LLM enrich skipped (import): {exc}")
        return meta

    if not bool(getattr(settings, "USE_LLM_METADATA", False)):
        return meta

    prompt = f"""You refine dataset metadata for an analytics copilot.
Return ONLY JSON with keys: title, description, summary, tags (array), keywords (array).
Prefer concise human titles like "India GDP" over generic names.
Do not invent countries or metrics not supported by the input.

Current title: {meta.title}
Topic: {meta.topic}
Domain: {meta.domain}
Countries: {meta.country}
Metrics: {meta.metrics}
Columns: {meta.columns}
Time column: {meta.time_column}
Primary entity: {meta.primary_entity}
User question: {question or ""}
Stats (sample): {str(stats)[:800]}
"""
    try:
        import json

        raw = invoke_llm(prompt)
        payload = None
        try:
            payload = json.loads(raw)
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                payload = json.loads(raw[start : end + 1])
        if not isinstance(payload, dict):
            meta.notes.append("LLM enrich: non-JSON response")
            return meta

        title = str(payload.get("title") or "").strip()
        if title and not is_placeholder_label(title):
            meta.title = title
            meta.topic = title
        if payload.get("description"):
            meta.description = str(payload["description"]).strip()
        if payload.get("summary"):
            meta.summary = str(payload["summary"]).strip()
        if isinstance(payload.get("tags"), list):
            for t in payload["tags"]:
                if t and str(t) not in meta.tags:
                    meta.tags.append(str(t))
        if isinstance(payload.get("keywords"), list):
            for k in payload["keywords"]:
                if k and str(k) not in meta.keywords:
                    meta.keywords.append(str(k))
        meta.generator = "rule_based+llm"
        meta.notes.append("LLM metadata enrichment applied")
    except Exception as exc:
        meta.notes.append(f"LLM enrich failed: {exc}")
        logger.warning("LLM metadata enrichment failed", extra={"error": str(exc)})
    return meta
