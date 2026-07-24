"""Data Engineer Agent — load local dataset + prepare DataFrame only.

Must NOT download from the internet or run multi-source search.
Expects `local_path` (or session in-memory data / upload file_path) from the
retrieval/prepare pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from backend.core.logger import get_logger
from backend.errors.error_types import DATASET_LOAD_FAILED, DATASET_NOT_FOUND
from backend.utils.data_acquisition import CONNECT_SOURCES_HINT, DEFAULT_ACQUISITION_OPTIONS
from backend.utils.dataset_loader import load_dataset

logger = get_logger(__name__)


def data_engineer_agent(state):
    """Load and prepare a dataset for analytics agents.

    Inputs (only):
      - local_path / file_path / existing state['data']
      - dataset_metadata (optional)

    Never downloads remote URLs or invokes search/retrieval.
    """
    logger.info(
        "Data engineer agent executing",
        extra={"action": "fetch_data", "question": state.get("question")},
    )

    must_reload = bool(state.get("force_reload_dataset") or state.get("topic_mismatch"))
    metadata = state.get("dataset_metadata") or {}

    # 1) Reuse in-memory frame for session continuity
    if state.get("data") is not None and not must_reload:
        prepared = _prepare_dataframe(state["data"], state)
        return _finalize_frame(state, prepared)

    # 2) Preferred: local_path from prepare pipeline
    local_path = state.get("local_path") or metadata.get("local_path")
    if local_path and Path(str(local_path)).is_file():
        return _load_local(state, str(local_path), source=state.get("source") or "local_library")

    # 3) User upload path
    file_path = state.get("file_path")
    if file_path and Path(str(file_path)).is_file() and not must_reload:
        return _load_local(state, str(file_path), source="user_upload")

    # 4) No remote download fallback — fail clearly
    topic = state.get("dataset_topic") or metadata.get("topic") or "this topic"
    message = (
        state.get("error")
        or f'No local dataset path available for "{topic}". '
        f"The acquisition/retrieval pipeline must provide a local_path. {CONNECT_SOURCES_HINT}"
    )
    state["error"] = message
    state["error_type"] = DATASET_NOT_FOUND
    state["answer"] = message
    state["data"] = None
    state["needs_user_data"] = True
    state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
    state["stop"] = True
    logger.warning(
        "Data engineer missing local_path",
        extra={"topic": topic, "local_path": local_path, "file_path": file_path},
    )
    return state


def _load_local(state, path: str, *, source: str):
    try:
        df = load_dataset(path)
        df = _prepare_dataframe(df, state)
        state["local_path"] = path
        state["source"] = source
        # Keep download_url in metadata if present, but do not fetch it
        return _finalize_frame(state, df)
    except Exception as exc:
        topic = state.get("dataset_topic") or "dataset"
        message = f'Could not load local dataset for "{topic}": {exc}. {CONNECT_SOURCES_HINT}'
        state["error"] = message
        state["error_type"] = DATASET_LOAD_FAILED
        state["data"] = None
        state["answer"] = message
        state["needs_user_data"] = True
        state["data_acquisition_options"] = list(DEFAULT_ACQUISITION_OPTIONS)
        state["stop"] = True
        logger.error("Local dataset load failed", extra={"path": path, "error": str(exc)})
        return state


def _finalize_frame(state, df: pd.DataFrame):
    state["data"] = df
    state["last_dataset"] = df
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()
    meta = state.get("dataset_metadata") or {}
    state["dataset_topic"] = state.get("dataset_topic") or meta.get("topic") or "dataset"
    if meta.get("download_url") and not state.get("dataset_url"):
        state["dataset_url"] = meta.get("download_url")
    if meta.get("dataset_id") and not state.get("dataset_id"):
        state["dataset_id"] = meta.get("dataset_id")
    state["source"] = state.get("source") or meta.get("source") or "local"
    state["data_ready"] = True
    state.pop("error", None)
    state["error_type"] = None
    logger.info(
        "Dataset prepared successfully",
        extra={
            "action": "fetch_data",
            "path": state.get("local_path"),
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
        },
    )
    return state


def _prepare_dataframe(df: pd.DataFrame, state) -> pd.DataFrame:
    prepared = df.copy()

    prepared.columns = [
        re.sub(r"\s+", " ", str(col)).strip() for col in prepared.columns
    ]

    prepared = prepared.dropna(axis=0, how="all")
    prepared = prepared.dropna(axis=1, how="all")

    for col in prepared.columns:
        lower = str(col).lower()
        if lower in {"year", "date", "time", "period"}:
            coerced = pd.to_numeric(prepared[col], errors="coerce")
            if coerced.notna().sum() >= max(1, int(0.5 * len(prepared))):
                prepared[col] = coerced
        elif lower in {"value", "gdp", "amount", "total", "population"}:
            prepared[col] = pd.to_numeric(prepared[col], errors="coerce")

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
        if re.search(
            pattern if pattern.startswith("\\") or " " in pattern else rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])",
            normalized,
        ):
            return label
    return None
