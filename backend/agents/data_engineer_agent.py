import re

import pandas as pd

from backend.agents.dataset_search_agent import dataset_search_agent
from backend.core.logger import get_logger
from backend.errors.error_types import DATASET_NOT_FOUND, DATASET_LOAD_FAILED
from backend.utils.dataset_loader import load_dataset

logger = get_logger(__name__)


def data_engineer_agent(state):
    """Download and prepare a dataset for downstream analytics agents.

    Responsibilities:
    - resolve dataset URL (via search if needed)
    - load CSV/Excel/JSON/Parquet
    - standardize columns
    - coerce types
    - optional country/entity filter from user focus
    - light cleaning (non-destructive)
    - expose a ready-to-analyze DataFrame on state
    """
    logger.info(
        "Data engineer agent executing",
        extra={"action": "fetch_data", "question": state.get("question")},
    )

    # Session / prior step already provided a frame — prepare in place, unless
    # the planner requested a reload for a newly named topic.
    if state.get("data") is not None and not state.get("force_reload_dataset"):
        prepared = _prepare_dataframe(state["data"], state)
        return _finalize_frame(state, prepared, dataset_url=state.get("dataset_url"))

    dataset_url = state.get("dataset_url") if not state.get("force_reload_dataset") else None
    if state.get("force_reload_dataset"):
        # Allow search to pick a fresh URL for the new topic.
        dataset_url = None

    if not dataset_url:
        state = dataset_search_agent(state)
        dataset_url = state.get("dataset_url")

    if not dataset_url:
        if state.get("file_path"):
            return state

        state["error"] = "I could not locate a suitable dataset for this topic."
        state["error_type"] = DATASET_NOT_FOUND
        if not state.get("answer"):
            state["answer"] = state["error"]
        return state

    logger.info(
        "Loading dataset",
        extra={"action": "fetch_data", "dataset": dataset_url},
    )

    try:
        df = load_dataset(dataset_url)
        df = _prepare_dataframe(df, state)
        return _finalize_frame(state, df, dataset_url=dataset_url)
    except Exception as e:
        state["error"] = f"Dataset loading failed: {str(e)}"
        state["error_type"] = DATASET_LOAD_FAILED
        state["data"] = None
        state["answer"] = state["error"]
        logger.error(
            "Dataset loading failed",
            extra={"action": "fetch_data", "dataset": dataset_url, "error": str(e)},
        )
        return state


def _finalize_frame(state, df: pd.DataFrame, dataset_url: str | None = None):
    state["data"] = df
    state["last_dataset"] = df
    if dataset_url:
        state["dataset_url"] = dataset_url
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()
    state["dataset_topic"] = state.get("dataset_topic") or "dataset discovery"
    state["source"] = state.get("source") or "dataset_discovery"
    state["data_ready"] = True
    state.pop("error", None)
    state["error_type"] = None
    logger.info(
        "Dataset prepared successfully",
        extra={
            "action": "fetch_data",
            "dataset": state.get("dataset_url"),
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
        },
    )
    return state


def _prepare_dataframe(df: pd.DataFrame, state) -> pd.DataFrame:
    prepared = df.copy()

    # Standardize column names: strip, collapse whitespace.
    prepared.columns = [
        re.sub(r"\s+", " ", str(col)).strip() for col in prepared.columns
    ]

    # Drop completely empty rows/columns only (non-destructive).
    prepared = prepared.dropna(axis=0, how="all")
    prepared = prepared.dropna(axis=1, how="all")

    # Coerce obvious year/value columns.
    for col in prepared.columns:
        lower = str(col).lower()
        if lower in {"year", "date", "time", "period"}:
            coerced = pd.to_numeric(prepared[col], errors="coerce")
            if coerced.notna().sum() >= max(1, int(0.5 * len(prepared))):
                prepared[col] = coerced
        elif lower in {"value", "gdp", "amount", "total", "population"}:
            prepared[col] = pd.to_numeric(prepared[col], errors="coerce")

    # Optional country focus (e.g. Analyze India's GDP).
    focus_country = state.get("focus_country")
    if not focus_country:
        focus_country = _infer_country_from_text(
            f"{state.get('question') or ''} {state.get('dataset_topic') or ''}"
        )

    country_col = _find_country_column(prepared)
    if focus_country and country_col:
        mask = prepared[country_col].astype(str).str.lower() == focus_country.lower()
        if not mask.any():
            mask = prepared[country_col].astype(str).str.contains(
                re.escape(focus_country), case=False, na=False
            )
        filtered = prepared.loc[mask]
        # Only apply filter when we still have a usable series.
        if not filtered.empty and len(filtered) >= 2:
            prepared = filtered.copy()
            state["focus_country"] = focus_country
            state.setdefault("insights", []).append(
                {
                    "data_engineering": {
                        "country_filter": focus_country,
                        "rows_after_filter": int(prepared.shape[0]),
                    }
                }
            )

    prepared = prepared.reset_index(drop=True)
    state["cleaned"] = True
    return prepared


def _find_country_column(df: pd.DataFrame):
    for col in df.columns:
        if str(col).strip().lower() in {
            "country name",
            "country",
            "country_name",
            "nation",
            "entity",
            "location",
        }:
            return col
    return None


def _infer_country_from_text(text: str) -> str | None:
    normalized = (text or "").lower()
    mapping = {
        "india": "India",
        "united states": "United States",
        "usa": "United States",
        r"\bus\b": "United States",
        "china": "China",
        "japan": "Japan",
        "germany": "Germany",
        "brazil": "Brazil",
        "united kingdom": "United Kingdom",
        r"\buk\b": "United Kingdom",
        "canada": "Canada",
        "france": "France",
        "australia": "Australia",
    }
    for pattern, label in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(pattern if pattern.startswith("\\") or " " in pattern else rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])", normalized):
            return label
    return None
