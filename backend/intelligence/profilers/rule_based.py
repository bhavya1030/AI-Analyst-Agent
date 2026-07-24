"""Rule-based structural profiler (no summary statistics, no charts)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backend.core.logger import get_logger
from backend.intelligence.exceptions import IntelligenceReadError, IntelligenceValidationError
from backend.intelligence.models import DatasetProfile, _utc_now_iso
from backend.intelligence.profilers.base import DatasetProfiler

logger = get_logger(__name__)

# Structural inspection only — sample rows for type inference, not full EDA stats.
_SAMPLE_ROWS = 200
_MAX_ROWS_FOR_COUNT = 2_000_000  # safety: still count but avoid pathological loads

TIME_NAME_TOKENS = {
    "date", "time", "datetime", "timestamp", "year", "month", "day", "period", "week",
}
ENTITY_NAME_TOKENS = {
    "country", "nation", "region", "state", "city", "entity", "name", "location",
    "iso", "code", "id", "symbol", "ticker",
}
GEO_NAME_TOKENS = {
    "lat", "latitude", "lon", "lng", "longitude", "geo", "geometry", "wkt", "coordinates",
}
TEXT_HINT_AVG_LEN = 40

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "economics": ["gdp", "inflation", "cpi", "unemployment", "trade", "export", "import", "economy"],
    "finance": ["price", "stock", "equity", "bond", "fx", "exchange", "interest", "gold", "silver", "oil"],
    "weather": ["temperature", "rainfall", "precipitation", "humidity", "climate", "weather"],
    "health": ["disease", "hospital", "mortality", "covid", "vaccine", "health", "cases"],
    "demographics": ["population", "birth", "death", "age", "gender", "migration"],
    "energy": ["energy", "electricity", "power", "coal", "gas", "renewable", "emission", "co2"],
    "education": ["school", "student", "literacy", "education", "enrollment"],
}

COUNTRY_HINTS = {
    "india", "china", "japan", "germany", "brazil", "canada", "france", "australia",
    "united states", "usa", "uk", "united kingdom", "mexico", "italy", "spain",
    "russia", "korea", "indonesia", "turkey", "saudi arabia", "south africa",
}


class RuleBasedProfiler(DatasetProfiler):
    name = "rule_based"

    def profile(self, local_path: str | Path) -> DatasetProfile:
        path = Path(local_path).expanduser()
        if not path.is_file():
            raise IntelligenceValidationError(f"Dataset file not found: {local_path}")

        file_format = path.suffix.lower().lstrip(".") or "unknown"
        try:
            df = _read_structure(path, file_format)
        except Exception as exc:
            raise IntelligenceReadError(f"Failed to inspect dataset: {exc}") from exc

        notes: list[str] = []
        columns = [str(c) for c in df.columns.tolist()]
        col_types = {str(c): _type_label(df[c]) for c in df.columns}

        numeric_metrics = [
            str(c)
            for c in df.columns
            if _is_numeric_series(df[c]) and not _looks_like_time_name(str(c))
        ]
        categorical_fields = [
            str(c)
            for c in df.columns
            if not _is_numeric_series(df[c]) and not _looks_like_time_name(str(c))
        ]

        time_column = _detect_time_column(df)
        entity_column = _detect_entity_column(df, time_column)
        date_range = _detect_date_range(df, time_column) if time_column else None
        countries = _detect_countries_regions(df, entity_column)
        keywords = _topic_keywords(columns, path.stem)
        domain = _detect_domain(columns, keywords, path.stem)
        dataset_type = _detect_dataset_type(
            df, columns, col_types, time_column, numeric_metrics, categorical_fields
        )

        # Row count: prefer shape; if sample-limited, note it
        row_count = int(df.attrs.get("row_count_estimate") or len(df))
        if df.attrs.get("sampled"):
            notes.append("Row count estimated from full scan or header metadata when available.")

        profile = DatasetProfile(
            dataset_type=dataset_type,
            row_count=row_count,
            column_names=columns,
            column_types=col_types,
            time_column=time_column,
            entity_column=entity_column,
            numeric_metrics=numeric_metrics,
            categorical_fields=categorical_fields,
            date_range=date_range,
            countries_regions=countries,
            topic_keywords=keywords,
            domain=domain,
            local_path=str(path.resolve()),
            file_format=file_format or "unknown",
            profiled_at=_utc_now_iso(),
            profiler=self.name,
            notes=notes,
        )
        logger.info(
            "Rule-based dataset profile created",
            extra={
                "path": str(path),
                "type": dataset_type,
                "rows": row_count,
                "cols": len(columns),
                "domain": domain,
            },
        )
        return profile


def _read_structure(path: Path, file_format: str) -> pd.DataFrame:
    """Load enough of the file to understand structure (not full EDA)."""
    fmt = file_format.lower()
    if fmt == "csv":
        # Count rows cheaply when possible
        row_count = _count_csv_rows(path)
        df = pd.read_csv(path, nrows=_SAMPLE_ROWS)
        df.attrs["row_count_estimate"] = row_count if row_count is not None else len(df)
        df.attrs["sampled"] = row_count is not None and row_count > len(df)
        return df
    if fmt == "json":
        try:
            df = pd.read_json(path)
        except Exception:
            df = pd.read_json(path, lines=True)
        df = df.head(_SAMPLE_ROWS) if len(df) > _SAMPLE_ROWS else df
        # re-read length if truncated
        try:
            full_len = len(pd.read_json(path) if path.stat().st_size < 5_000_000 else df)
        except Exception:
            full_len = len(df)
        df.attrs["row_count_estimate"] = full_len
        df.attrs["sampled"] = full_len > len(df)
        return df
    if fmt in {"xlsx", "xls"}:
        df = pd.read_excel(path, nrows=_SAMPLE_ROWS)
        try:
            full = pd.read_excel(path)
            df.attrs["row_count_estimate"] = len(full)
            df.attrs["sampled"] = len(full) > len(df)
        except Exception:
            df.attrs["row_count_estimate"] = len(df)
            df.attrs["sampled"] = False
        return df
    if fmt == "parquet":
        df = pd.read_parquet(path)
        total = len(df)
        if total > _SAMPLE_ROWS:
            sample = df.head(_SAMPLE_ROWS).copy()
            sample.attrs["row_count_estimate"] = total
            sample.attrs["sampled"] = True
            return sample
        df.attrs["row_count_estimate"] = total
        df.attrs["sampled"] = False
        return df

    # Fallback try csv
    df = pd.read_csv(path, nrows=_SAMPLE_ROWS)
    df.attrs["row_count_estimate"] = len(df)
    df.attrs["sampled"] = True
    return df


def _count_csv_rows(path: Path) -> Optional[int]:
    try:
        with path.open("rb") as f:
            # subtract header
            count = sum(1 for _ in f)
        return max(0, count - 1)
    except Exception:
        return None


def _type_label(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    # try parse datetime from object
    if series.dtype == object:
        sample = series.dropna().astype(str).head(20)
        if not sample.empty:
            parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() >= 0.8:
                return "datetime"
        return "string"
    return str(series.dtype)


def _is_numeric_series(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return True
    if series.dtype == object:
        coerced = pd.to_numeric(series, errors="coerce")
        return coerced.notna().mean() >= 0.8 if len(series) else False
    return False


def _looks_like_time_name(name: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
    return bool(tokens & TIME_NAME_TOKENS)


def _detect_time_column(df: pd.DataFrame) -> Optional[str]:
    # Name-based first
    for col in df.columns:
        if _looks_like_time_name(str(col)):
            return str(col)
    # dtype datetime
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return str(col)
    # parseable object/numeric year
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            vals = pd.to_numeric(series, errors="coerce").dropna()
            if len(vals) >= 3 and vals.between(1800, 2100).mean() >= 0.9 and vals.nunique() >= 3:
                return str(col)
        if series.dtype == object:
            sample = series.dropna().astype(str).head(30)
            if sample.empty:
                continue
            parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() >= 0.8:
                return str(col)
    return None


def _detect_entity_column(df: pd.DataFrame, time_column: Optional[str]) -> Optional[str]:
    best = None
    best_score = -1
    for col in df.columns:
        name = str(col)
        if time_column and name == time_column:
            continue
        if _is_numeric_series(df[col]) and not _name_has_entity_token(name):
            continue
        score = 0
        tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
        if tokens & ENTITY_NAME_TOKENS:
            score += 5
        nunique = df[col].nunique(dropna=True)
        n = max(1, len(df))
        ratio = nunique / n
        # entity-like: moderate cardinality
        if 1 < nunique <= max(3, int(0.5 * n)):
            score += 2
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            score += 1
        if score > best_score:
            best_score = score
            best = name
    return best if best_score > 0 else None


def _name_has_entity_token(name: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
    return bool(tokens & ENTITY_NAME_TOKENS)


def _detect_date_range(df: pd.DataFrame, time_column: str) -> Optional[dict[str, Any]]:
    series = df[time_column]
    try:
        if pd.api.types.is_numeric_dtype(series):
            vals = pd.to_numeric(series, errors="coerce").dropna()
            if vals.empty:
                return None
            if vals.between(1800, 2100).mean() >= 0.8:
                return {"start": str(int(vals.min())), "end": str(int(vals.max()))}
        parsed = pd.to_datetime(series, errors="coerce")
        parsed = parsed.dropna()
        if parsed.empty:
            return None
        return {
            "start": parsed.min().isoformat(),
            "end": parsed.max().isoformat(),
        }
    except Exception:
        return None


def _detect_countries_regions(df: pd.DataFrame, entity_column: Optional[str]) -> list[str]:
    found: list[str] = []
    cols = [entity_column] if entity_column else []
    cols.extend(str(c) for c in df.columns if str(c) not in cols)

    for col in cols[:5]:
        if col is None or col not in df.columns:
            continue
        sample = df[col].dropna().astype(str).head(50)
        for value in sample:
            low = value.strip().lower()
            for country in COUNTRY_HINTS:
                if country in low or low == country:
                    label = value.strip()
                    if label and label not in found:
                        found.append(label)
        if found:
            break
    return found[:20]


def _topic_keywords(columns: list[str], stem: str) -> list[str]:
    words: list[str] = []
    blob = " ".join(columns) + " " + stem.replace("_", " ").replace("-", " ")
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", blob.lower()):
        if token not in words and token not in {"the", "and", "for", "data", "dataset", "unnamed"}:
            words.append(token)
    return words[:15]


def _detect_domain(columns: list[str], keywords: list[str], stem: str) -> str:
    blob = " ".join(columns + keywords + [stem]).lower()
    scores = {domain: 0 for domain in DOMAIN_KEYWORDS}
    for domain, keys in DOMAIN_KEYWORDS.items():
        for key in keys:
            if key in blob:
                scores[domain] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def _detect_dataset_type(
    df: pd.DataFrame,
    columns: list[str],
    col_types: dict[str, str],
    time_column: Optional[str],
    numeric_metrics: list[str],
    categorical_fields: list[str],
) -> str:
    # Geospatial
    geo_hits = 0
    for col in columns:
        tokens = set(re.findall(r"[a-z0-9]+", col.lower()))
        if tokens & GEO_NAME_TOKENS:
            geo_hits += 1
    if geo_hits >= 2 or any(t in {"geometry", "wkt"} for t in col_types.values()):
        return "geospatial"

    # Text-heavy
    textish = 0
    for col in columns:
        series = df[col]
        if series.dtype == object or pd.api.types.is_string_dtype(series):
            sample = series.dropna().astype(str).head(30)
            if not sample.empty and sample.map(len).mean() >= TEXT_HINT_AVG_LEN:
                textish += 1
    if textish >= max(1, len(columns) // 2) and not time_column:
        return "text"

    # Time series
    if time_column and numeric_metrics:
        return "time_series"

    # Default tabular
    if columns:
        return "tabular"
    return "unknown"
