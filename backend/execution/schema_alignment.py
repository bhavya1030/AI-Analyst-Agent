"""Schema alignment — detect roles and normalize column names across datasets.

Does NOT compute statistics, charts, or EDA.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

import pandas as pd

from backend.core.logger import get_logger
from backend.execution.models import ColumnRoleHints, SchemaAlignmentResult

logger = get_logger(__name__)

# Canonical targets for common synonyms (lowered key → canonical name)
_CANONICAL_MAP: dict[str, str] = {
    # Country / nation
    "country": "Country",
    "country name": "Country",
    "country_name": "Country",
    "countryname": "Country",
    "nation": "Country",
    "nation name": "Country",
    "country code": "Country Code",
    "country_code": "Country Code",
    "iso": "Country Code",
    "iso3": "Country Code",
    "iso2": "Country Code",
    # Time
    "year": "Year",
    "yr": "Year",
    "fiscal year": "Year",
    "fiscal_year": "Year",
    "fiscalyear": "Year",
    "calendar year": "Year",
    "date": "Date",
    "datetime": "Date",
    "timestamp": "Date",
    "time": "Date",
    "period": "Year",
    "month": "Month",
    "day": "Day",
    # State / region
    "state": "State",
    "state name": "State",
    "state_name": "State",
    "province": "State",
    "region": "Region",
    "area": "Region",
    "area name": "Region",
    # City
    "city": "City",
    "city name": "City",
    # Generic entity
    "entity": "Entity",
    "entity name": "Entity",
    "name": "Name",
    "location": "Location",
    # Common metrics kept distinct when possible (suffix applied per dataset)
    "value": "Value",
    "gdp": "GDP",
    "population": "Population",
    "inflation": "Inflation",
    "cpi": "CPI",
}

_COUNTRY_TOKENS = frozenset(
    {"country", "nation", "iso", "iso3", "iso2", "country_name", "countryname"}
)
_STATE_TOKENS = frozenset({"state", "province", "region", "state_name"})
_TIME_TOKENS = frozenset(
    {
        "year",
        "yr",
        "date",
        "datetime",
        "timestamp",
        "time",
        "period",
        "month",
        "day",
        "fiscal",
        "fiscal_year",
        "fiscalyear",
    }
)
_ENTITY_TOKENS = frozenset(
    {
        "country",
        "nation",
        "state",
        "province",
        "region",
        "city",
        "entity",
        "location",
        "name",
        "id",
        "code",
        "symbol",
        "ticker",
        "iso",
    }
)


def _norm_key(name: str) -> str:
    s = re.sub(r"[_\-]+", " ", str(name).strip().lower())
    s = re.sub(r"\s+", " ", s)
    return s


def canonicalize_column_name(name: str) -> str:
    """Map a column name to a canonical form when known; otherwise title-case lightly."""
    key = _norm_key(name)
    if key in _CANONICAL_MAP:
        return _CANONICAL_MAP[key]
    # Multi-token partial: "Country Name (English)" → try first meaningful tokens
    if key.startswith("country name") or key == "country name":
        return "Country"
    if "fiscal year" in key or key.endswith(" year") and "year" in key.split():
        if "month" not in key:
            return "Year"
    if key in {"countryname", "country_name"}:
        return "Country"
    # Preserve original if no mapping
    return str(name).strip()


def detect_column_roles(columns: Sequence[str]) -> ColumnRoleHints:
    """Detect semantic roles for a single column set."""
    hints = ColumnRoleHints()
    for col in columns:
        key = _norm_key(col)
        tokens = set(key.replace("-", " ").split())
        # Country
        if tokens & _COUNTRY_TOKENS or key in {"country", "nation", "country name"}:
            hints.country_columns.append(str(col))
            if str(col) not in hints.entity_columns:
                hints.entity_columns.append(str(col))
            continue
        # State
        if tokens & _STATE_TOKENS and "country" not in tokens:
            hints.state_columns.append(str(col))
            if str(col) not in hints.entity_columns:
                hints.entity_columns.append(str(col))
            continue
        # Time
        if tokens & _TIME_TOKENS or key in _TIME_TOKENS:
            hints.time_columns.append(str(col))
            continue
        # Broader entity
        if tokens & _ENTITY_TOKENS:
            if str(col) not in hints.entity_columns:
                hints.entity_columns.append(str(col))
            continue
        # Treat remaining as potential metrics (caller may refine with dtypes)
        hints.metric_columns.append(str(col))
    return hints


class SchemaAlignmentService:
    """
    Align schemas across multiple DataFrames for merge.

    Responsibilities:
      - detect common / entity / time / country / state columns
      - normalize column names to canonical forms
      - propose join keys
    """

    def align(
        self,
        frames: Sequence[pd.DataFrame],
        *,
        topics: Optional[Sequence[str]] = None,
        profiles: Optional[Sequence[Optional[dict]]] = None,
    ) -> SchemaAlignmentResult:
        if not frames:
            return SchemaAlignmentResult(warnings=["No frames to align."])

        topic_list = list(topics) if topics else [f"dataset_{i}" for i in range(len(frames))]
        while len(topic_list) < len(frames):
            topic_list.append(f"dataset_{len(topic_list)}")

        profile_list: list[Optional[dict]] = list(profiles) if profiles else [None] * len(frames)
        while len(profile_list) < len(frames):
            profile_list.append(None)

        rename_maps: list[dict[str, str]] = []
        aligned: list[pd.DataFrame] = []
        warnings: list[str] = []

        # Per-frame renames to canonical names
        for i, df in enumerate(frames):
            rename = self._build_rename_map(df, topic=topic_list[i], index=i)
            rename_maps.append(rename)
            out = df.rename(columns=rename).copy()
            # Disambiguate non-key metric collisions later; first pass keep names
            aligned.append(out)

        # Disambiguate overlapping non-key columns with topic suffixes
        join_keys = self._propose_join_keys(aligned, profile_list)
        aligned = self._suffix_conflicting_metrics(aligned, join_keys, topic_list, warnings)

        # Aggregate role hints on aligned columns
        all_cols = [str(c) for df in aligned for c in df.columns]
        unique_cols = list(dict.fromkeys(all_cols))
        role_hints = detect_column_roles(unique_cols)

        # Common columns across all frames
        if aligned:
            common = set(str(c) for c in aligned[0].columns)
            for df in aligned[1:]:
                common &= set(str(c) for c in df.columns)
            role_hints.common_columns = sorted(common)

        # Prefer join keys that still exist after suffixing
        join_keys = [k for k in join_keys if all(k in df.columns for df in aligned)]
        if not join_keys and len(aligned) > 1:
            warnings.append(
                "No shared join keys detected after alignment; merger may fall back to concat."
            )

        logger.info(
            "Schema alignment complete",
            extra={
                "n_frames": len(aligned),
                "join_keys": join_keys,
                "common": role_hints.common_columns,
            },
        )

        return SchemaAlignmentResult(
            aligned_frames=aligned,
            rename_maps=rename_maps,
            role_hints=role_hints,
            join_keys=join_keys,
            warnings=warnings,
            topics=topic_list[: len(aligned)],
        )

    def _build_rename_map(
        self,
        df: pd.DataFrame,
        *,
        topic: str,
        index: int,
    ) -> dict[str, str]:
        rename: dict[str, str] = {}
        used: set[str] = set()
        for col in df.columns:
            original = str(col)
            canonical = canonicalize_column_name(original)
            # Avoid collapsing two different originals into same target within one frame
            if canonical in used and canonical != original:
                # Prefer first mapping; keep second with mild disambiguation
                alt = f"{canonical}_{index}"
                if alt in used:
                    alt = f"{canonical}_{topic}"[:40]
                rename[original] = alt
                used.add(alt)
            else:
                rename[original] = canonical
                used.add(canonical)
        return rename

    def _propose_join_keys(
        self,
        frames: Sequence[pd.DataFrame],
        profiles: Sequence[Optional[dict]],
    ) -> list[str]:
        """Propose join keys: Country+Year for time series, else entity columns."""
        if len(frames) < 2:
            return []

        # Profile-driven time/entity hints
        time_from_profile: list[str] = []
        entity_from_profile: list[str] = []
        types: list[str] = []
        for p in profiles:
            if not p:
                continue
            if p.get("time_column"):
                time_from_profile.append(canonicalize_column_name(str(p["time_column"])))
            if p.get("entity_column"):
                entity_from_profile.append(canonicalize_column_name(str(p["entity_column"])))
            if p.get("dataset_type"):
                types.append(str(p["dataset_type"]))

        # Detect columns present in ALL frames
        common = set(str(c) for c in frames[0].columns)
        for df in frames[1:]:
            common &= set(str(c) for c in df.columns)

        keys: list[str] = []

        # Time-series style: Country + Year
        has_country = "Country" in common or any(c in common for c in ("Country Code", "Nation"))
        has_year = "Year" in common
        has_date = "Date" in common
        looks_ts = "time_series" in types or has_year or has_date

        if looks_ts and has_year:
            if "Country" in common:
                keys = ["Country", "Year"]
            elif "Country Code" in common:
                keys = ["Country Code", "Year"]
            elif "State" in common:
                keys = ["State", "Year"]
            else:
                keys = ["Year"]
            # Include entity from profile if in common
            for e in entity_from_profile:
                if e in common and e not in keys:
                    keys.insert(0, e)
            return list(dict.fromkeys(keys))

        if looks_ts and has_date:
            if "Country" in common:
                return ["Country", "Date"]
            if "State" in common:
                return ["State", "Date"]
            return ["Date"]

        # Entity-based
        for candidate in ("Country", "Country Code", "State", "Region", "City", "Entity", "Name"):
            if candidate in common:
                keys.append(candidate)
        for e in entity_from_profile:
            if e in common and e not in keys:
                keys.append(e)

        # Shared time column if any
        for t in ("Year", "Date", "Month"):
            if t in common and t not in keys:
                keys.append(t)

        if keys:
            return keys

        # Fall back to all common non-pure-metric looking columns
        roles = detect_column_roles(sorted(common))
        for col in roles.entity_columns + roles.time_columns + roles.country_columns:
            if col in common and col not in keys:
                keys.append(col)
        return keys

    def _suffix_conflicting_metrics(
        self,
        frames: list[pd.DataFrame],
        join_keys: Sequence[str],
        topics: Sequence[str],
        warnings: list[str],
    ) -> list[pd.DataFrame]:
        """Rename non-key columns that appear in multiple frames to include topic suffix."""
        if len(frames) < 2:
            return frames

        key_set = set(join_keys)
        # Count non-key column name frequency
        from collections import Counter

        non_key_counts: Counter[str] = Counter()
        for df in frames:
            for c in df.columns:
                name = str(c)
                if name not in key_set:
                    non_key_counts[name] += 1

        conflicts = {name for name, n in non_key_counts.items() if n > 1}
        if not conflicts:
            return frames

        out: list[pd.DataFrame] = []
        for i, df in enumerate(frames):
            topic = topics[i] if i < len(topics) else f"ds{i}"
            safe_topic = re.sub(r"[^\w]+", "_", topic.strip())[:32].strip("_") or f"ds{i}"
            rename: dict[str, str] = {}
            for c in df.columns:
                name = str(c)
                if name in conflicts:
                    new_name = f"{name}_{safe_topic}"
                    rename[name] = new_name
            if rename:
                warnings.append(
                    f"Disambiguated overlapping columns for '{topic}': {rename}"
                )
                out.append(df.rename(columns=rename))
            else:
                out.append(df)
        return out


def detect_common_columns(frames: Iterable[pd.DataFrame]) -> list[str]:
    frames = list(frames)
    if not frames:
        return []
    common = set(str(c) for c in frames[0].columns)
    for df in frames[1:]:
        common &= set(str(c) for c in df.columns)
    return sorted(common)
