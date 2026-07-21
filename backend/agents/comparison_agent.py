import re

import pandas as pd
import plotly.express as px

from backend.config import settings
from backend.core.logger import get_logger
from backend.errors.error_types import COMPARISON_FAILED
from backend.utils.dataset_loader import load_dataset
from backend.utils.json_safe import figure_to_json

logger = get_logger(__name__)

DATASET_SOURCES = settings.DATASET_SOURCES

# Canonical country labels used for matching against dataset country columns.
COUNTRY_ALIASES = {
    "india": "India",
    "ind": "India",
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "america": "United States",
    "china": "China",
    "prc": "China",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "great britain": "United Kingdom",
    "japan": "Japan",
    "germany": "Germany",
    "france": "France",
    "brazil": "Brazil",
    "canada": "Canada",
    "australia": "Australia",
    "russia": "Russian Federation",
    "russian federation": "Russian Federation",
    "south korea": "Korea, Rep.",
    "korea": "Korea, Rep.",
    "mexico": "Mexico",
    "indonesia": "Indonesia",
    "italy": "Italy",
    "spain": "Spain",
    "south africa": "South Africa",
    "nigeria": "Nigeria",
    "pakistan": "Pakistan",
    "bangladesh": "Bangladesh",
    "saudi arabia": "Saudi Arabia",
    "turkey": "Turkiye",
    "turkiye": "Turkiye",
}


def detect_requested_datasets(question):
    question = question.lower()
    selected = []
    for keyword in DATASET_SOURCES:
        if keyword in question:
            selected.append(keyword)
    return selected


def detect_requested_countries(question: str) -> list[str]:
    """Extract comparison countries from free text using aliases."""
    text = (question or "").lower()
    if not text:
        return []

    found: list[str] = []
    # Longer phrases first so "united states" wins over "us".
    aliases = sorted(COUNTRY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
    matched_spans: list[tuple[int, int]] = []

    for alias, canonical in aliases:
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        for match in re.finditer(pattern, text):
            span = match.span()
            if any(not (span[1] <= s or span[0] >= e) for s, e in matched_spans):
                continue
            if canonical not in found:
                found.append(canonical)
            matched_spans.append(span)

    return found


def _find_column(df: pd.DataFrame, candidates: set[str]):
    for col in df.columns:
        if str(col).strip().lower() in candidates:
            return col
    return None


def _find_country_column(df: pd.DataFrame):
    return _find_column(
        df,
        {
            "country name",
            "country",
            "country_name",
            "nation",
            "entity",
            "location",
            "area",
        },
    )


def _find_year_column(df: pd.DataFrame):
    year_col = _find_column(df, {"year", "date", "time", "period"})
    if year_col is not None:
        return year_col
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    return None


def _find_value_column(df: pd.DataFrame, year_col, country_col):
    value_col = _find_column(df, {"value", "gdp", "amount", "total"})
    if value_col is not None:
        return value_col
    for col in df.columns:
        if col in {year_col, country_col}:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            return col
    return None


def _resolve_countries_in_frame(df: pd.DataFrame, country_col: str, requested: list[str]) -> list[str]:
    available = {
        str(name).strip(): str(name).strip()
        for name in df[country_col].dropna().unique()
    }
    available_lower = {name.lower(): name for name in available}

    resolved = []
    for country in requested:
        key = country.lower()
        if key in available_lower:
            resolved.append(available_lower[key])
            continue
        # Partial match (e.g. "Korea" -> "Korea, Rep.")
        partial = [
            name
            for lower_name, name in available_lower.items()
            if key in lower_name or lower_name in key
        ]
        if partial:
            resolved.append(partial[0])
    # Preserve order, drop duplicates
    deduped = []
    for name in resolved:
        if name not in deduped:
            deduped.append(name)
    return deduped


def _load_metric_frame(state, metric: str, required_countries: list[str] | None = None) -> pd.DataFrame | None:
    """Load a frame suitable for comparison.

    If the active session frame was country-filtered (e.g. India-only GDP), it
    cannot support India vs US. In that case reload the full metric source.
    """
    data = state.get("data")
    required_countries = required_countries or []

    if data is not None and _find_country_column(data) is not None:
        country_col = _find_country_column(data)
        if required_countries:
            resolved = _resolve_countries_in_frame(data, country_col, required_countries)
            if len(resolved) >= len(required_countries):
                return data.copy()
            # Session frame is too narrow (likely a prior country filter).
            logger.info(
                "Session frame missing comparison countries; reloading full metric source",
                extra={
                    "action": "compare_datasets",
                    "required": required_countries,
                    "found": resolved,
                    "metric": metric,
                },
            )
        else:
            return data.copy()

    url = (
        state.get("dataset_url")
        if state.get("dataset_url") and not required_countries
        else None
    )
    url = url or DATASET_SOURCES.get(metric) or DATASET_SOURCES.get("gdp")
    if not url:
        return None
    return load_dataset(url)


def _compare_countries(state, question: str, countries: list[str]):
    metrics = detect_requested_datasets(question)
    metric = metrics[0] if metrics else (state.get("dataset_topic") or "gdp")
    if isinstance(metric, str):
        metric = metric.lower().strip() or "gdp"
    if metric not in DATASET_SOURCES:
        metric = "gdp" if "gdp" in (question or "").lower() or not metrics else metrics[0]

    try:
        df = _load_metric_frame(
            state,
            metric if metric in DATASET_SOURCES else "gdp",
            required_countries=countries,
        )
    except Exception as exc:
        state["answer"] = f"Could not load dataset for country comparison: {exc}"
        state["error"] = str(exc)
        state["error_type"] = COMPARISON_FAILED
        return state

    if df is None or df.empty:
        state["answer"] = "Could not load a dataset for country comparison."
        return state

    country_col = _find_country_column(df)
    year_col = _find_year_column(df)
    value_col = _find_value_column(df, year_col, country_col)

    if not country_col or not year_col or not value_col:
        state["answer"] = (
            "Country comparison needs country, year, and value columns in the dataset."
        )
        return state

    resolved = _resolve_countries_in_frame(df, country_col, countries)
    if len(resolved) < 2:
        state["answer"] = (
            "Could not find enough matching countries in the dataset to compare. "
            f"Requested: {', '.join(countries)}."
        )
        return state

    subset = df[df[country_col].isin(resolved)].copy()
    subset[year_col] = pd.to_numeric(subset[year_col], errors="coerce")
    subset[value_col] = pd.to_numeric(subset[value_col], errors="coerce")
    subset = subset.dropna(subset=[year_col, value_col])

    if subset.empty:
        state["answer"] = "No overlapping numeric data found for the requested countries."
        return state

    # Aggregate duplicates (same country/year) if present.
    plot_df = (
        subset.groupby([year_col, country_col], as_index=False)[value_col]
        .mean()
        .sort_values(year_col)
    )

    metric_label = metric.upper() if isinstance(metric, str) else "VALUE"
    title = f"{metric_label} comparison: {' vs '.join(resolved)}"
    fig = px.line(
        plot_df,
        x=year_col,
        y=value_col,
        color=country_col,
        markers=True,
        title=title,
        labels={
            str(year_col): "Year",
            str(value_col): metric_label,
            str(country_col): "Country",
        },
    )
    fig.update_layout(legend_title_text="Country")

    chart = figure_to_json(fig)
    state["chart"] = chart
    state["charts"] = [chart]
    state["chart_columns_used"] = [str(year_col), str(value_col), str(country_col)]
    state["last_chart_type"] = "line"
    state["last_operation"] = "comparison"
    state["rows"] = int(plot_df.shape[0])
    state["columns"] = [str(c) for c in plot_df.columns.tolist()]
    state["data"] = plot_df

    # Latest-year snapshot for the answer text.
    latest_year = plot_df[year_col].max()
    latest = plot_df[plot_df[year_col] == latest_year]
    latest_bits = []
    for _, row in latest.iterrows():
        latest_bits.append(f"{row[country_col]}={row[value_col]:,.0f}")

    year_min = int(plot_df[year_col].min())
    year_max = int(plot_df[year_col].max())
    state["answer"] = (
        f"Compared {metric_label} for {' and '.join(resolved)} "
        f"from {year_min} to {year_max}. "
        f"Latest ({int(latest_year)}): {'; '.join(latest_bits)}. "
        "A line chart of the trend is included."
    )
    state.pop("error", None)
    state["error_type"] = None

    logger.info(
        "Country comparison completed",
        extra={
            "action": "compare_datasets",
            "countries": resolved,
            "metric": metric,
            "rows": int(plot_df.shape[0]),
        },
    )
    return state


def _compare_metric_datasets(state, datasets: list[str]):
    dfs = {}

    for name in datasets:
        url = DATASET_SOURCES[name]
        try:
            df = load_dataset(url)

            year_column = next(
                (col for col in df.columns if col.lower() == "year"),
                None,
            )

            if year_column is None:
                continue

            country_col = _find_country_column(df)
            if country_col is not None:
                # Global mean across countries per year for metric-vs-metric compare.
                df = df.groupby(year_column).mean(numeric_only=True).reset_index()
            else:
                df = df.groupby(year_column).mean(numeric_only=True).reset_index()

            df = df.rename(columns={year_column: "year"})

            if "value" not in [col.lower() for col in df.columns]:
                numeric_cols = [
                    col
                    for col in df.columns
                    if col.lower() != "year" and pd.api.types.is_numeric_dtype(df[col])
                ]
                if not numeric_cols:
                    continue
                df = df.rename(columns={numeric_cols[0]: name})
            else:
                value_col = next(col for col in df.columns if col.lower() == "value")
                df = df.rename(columns={value_col: name})

            keep_cols = ["year", name]
            dfs[name] = df[keep_cols]
        except Exception:
            continue

    if len(dfs) < 2:
        state["answer"] = "Could not load enough datasets for comparison."
        return state

    merged = None
    for _, frame in dfs.items():
        if merged is None:
            merged = frame
        else:
            merged = pd.merge(merged, frame, on="year", how="inner")

    if merged is None or merged.empty:
        state["answer"] = "Comparison failed because the datasets do not share overlapping years."
        state["chart"] = None
        return state

    numeric_cols = [col for col in merged.columns if col != "year"]
    if len(numeric_cols) < 2:
        state["answer"] = "Comparison failed due to missing numeric overlap."
        return state

    x = numeric_cols[0]
    y = numeric_cols[1]
    corr = merged[x].corr(merged[y])

    # Dual-axis style line chart over years plus scatter for correlation context.
    long_df = merged.melt(id_vars=["year"], value_vars=numeric_cols, var_name="metric", value_name="value")
    fig = px.line(
        long_df,
        x="year",
        y="value",
        color="metric",
        markers=True,
        title=f"Comparison: {' vs '.join(numeric_cols)}",
    )

    chart = figure_to_json(fig)
    state["chart"] = chart
    state["charts"] = [chart]
    state["chart_columns_used"] = ["year", x, y]
    state["last_chart_type"] = "line"
    state["last_operation"] = "comparison"
    state["rows"] = int(merged.shape[0])
    state["columns"] = merged.columns.tolist()

    if pd.isna(corr):
        state["answer"] = (
            f"Comparison chart created for {x} and {y}, but correlation could not be computed."
        )
    else:
        state["answer"] = f"Correlation between {x} and {y} is {round(corr, 3)}. A comparison chart is included."

    return state


def comparison_agent(state):
    try:
        question = (state.get("question") or "").lower()
        logger.info(
            "Comparison agent executing",
            extra={"action": "compare_datasets", "question": state.get("question")},
        )

        countries = detect_requested_countries(state.get("question") or "")
        datasets = detect_requested_datasets(question)

        # Country-vs-country comparison (e.g. India vs US GDP).
        if len(countries) >= 2:
            return _compare_countries(state, question, countries)

        # Metric-vs-metric comparison (e.g. GDP vs Population).
        if len(datasets) >= 2:
            return _compare_metric_datasets(state, datasets)

        if len(countries) == 1 and datasets:
            state["answer"] = (
                "Please specify at least two countries to compare "
                f"(only found: {countries[0]})."
            )
            return state

        if len(datasets) == 1:
            state["answer"] = (
                "Please specify at least two datasets to compare "
                f"(only found: {datasets[0]}), or two countries for a country-level comparison."
            )
            return state

        state["answer"] = (
            "Please specify at least two datasets (e.g. GDP and population) "
            "or two countries (e.g. India and United States) to compare."
        )
        return state
    except Exception as exc:
        state["chart"] = None
        state["chart_columns_used"] = []
        state["answer"] = "Comparison failed."
        state["error"] = f"Comparison failed: {exc}"
        state["error_type"] = COMPARISON_FAILED
        logger.error(
            "Comparison failed",
            extra={"action": "compare_datasets", "error": str(exc)},
        )
        return state
