"""Visualization agent v2 — inference, validation, safe fallbacks, durable cache."""

from __future__ import annotations

import hashlib

from backend.cache.analysis_cache import KIND_CHART, get_analysis_cache
from backend.cache.fingerprint import compute_dataset_fingerprint
from backend.core.logger import get_logger
from backend.errors.error_types import VISUALIZATION_FAILED
from backend.utils.json_safe import figure_to_json
from backend.visualization.builder import build_chart_safe
from backend.visualization.inference import detect_requested_chart_type

logger = get_logger(__name__)


def _serialize_chart(fig, chart_type, used_cols):
    return {
        "type": chart_type,
        "figure": figure_to_json(fig),
        "columns_used": used_cols,
    }


def _question_sig(question: str) -> str:
    normalized = " ".join((question or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _chart_params(
    *,
    mode: str,
    chart_type: str,
    columns: list[str],
    question: str = "",
) -> dict:
    return {
        "mode": mode,
        "chart_type": chart_type,
        "columns": sorted(str(c) for c in (columns or [])),
        "question_sig": _question_sig(question) if mode == "single" else "multi",
        "viz_version": 2,
    }


def _apply_cached_charts(state, payload: dict, *, multi: bool) -> dict:
    if multi:
        charts = payload.get("charts") or []
        state["charts"] = charts
        state["chart"] = charts[0]["figure"] if charts else None
        state["chart_columns_used"] = list(payload.get("chart_columns_used") or [])
        state["last_chart_type"] = payload.get("last_chart_type") or "multi"
        state["last_columns_used"] = list(
            payload.get("last_columns_used") or state["chart_columns_used"]
        )
    else:
        state["chart"] = payload.get("chart")
        state["chart_columns_used"] = list(payload.get("chart_columns_used") or [])
        state["last_chart_type"] = payload.get("last_chart_type") or "visualization"
        if payload.get("last_column_used") is not None:
            state["last_column_used"] = payload.get("last_column_used")
        if payload.get("last_columns_used") is not None:
            state["last_columns_used"] = list(payload.get("last_columns_used") or [])
        if state.get("chart") and not state.get("charts"):
            state["charts"] = [
                {
                    "type": state.get("last_chart_type") or "visualization",
                    "figure": state["chart"],
                    "columns_used": state.get("chart_columns_used") or [],
                }
            ]
        # Restore v2 metadata when present
        if payload.get("chart_spec") is not None:
            state["chart_spec"] = payload.get("chart_spec")
        if payload.get("chart_validation") is not None:
            state["chart_validation"] = payload.get("chart_validation")
        if payload.get("chart_recommendation"):
            state["chart_recommendation"] = payload.get("chart_recommendation")
    state["chart_from_cache"] = True
    return state


def _fig_to_state_json(fig):
    """Prefer plotly JSON dict (legacy tests / clients)."""
    try:
        return fig.to_plotly_json()
    except Exception:
        return figure_to_json(fig)


def run_multi_viz_agent(state):
    df = state.get("data")
    if df is None:
        state["charts"] = []
        return state

    reference = state.get("dataset_url") or state.get("file_path") or state.get("local_path")
    fingerprint = state.get("dataset_fingerprint") or compute_dataset_fingerprint(
        df, reference
    )
    state["dataset_fingerprint"] = fingerprint

    profile = state.get("dataset_profile", {}) or {}
    time_cols = list(profile.get("time_columns") or [])

    # Deterministic multi-chart set via safe builders
    plan_types = ["line", "histogram", "heatmap", "bar"]
    preview_cols: list[str] = list(df.columns.astype(str)[:8])

    params = _chart_params(
        mode="multi",
        chart_type="multi",
        columns=preview_cols,
    )
    cached = get_analysis_cache().get(KIND_CHART, fingerprint, params)
    if cached is not None:
        _apply_cached_charts(state, cached, multi=True)
        state["rows"] = int(df.shape[0])
        state["columns"] = df.columns.tolist()
        logger.info(
            "Multi visualization served from durable cache",
            extra={
                "action": "run_multi_viz",
                "dataset": reference,
                "fingerprint": fingerprint[:16],
                "chart_count": len(state.get("charts") or []),
            },
        )
        return state

    charts = []
    used_columns: list[str] = []
    for preferred in plan_types:
        built = build_chart_safe(
            df,
            question=state.get("question") or "",
            preferred_type=preferred,
            time_columns=time_cols,
        )
        fig = built.get("fig")
        spec = built.get("spec")
        if fig is None or spec is None:
            continue
        cols = spec.used_columns
        if not cols:
            continue
        # Avoid duplicate types
        if any(c.get("type") == spec.chart_type for c in charts):
            continue
        charts.append(_serialize_chart(fig, spec.chart_type, cols))
        used_columns.extend(cols)
        preview_cols.extend(cols)

    state["charts"] = charts
    state["chart"] = charts[0]["figure"] if charts else None
    state["chart_columns_used"] = list(dict.fromkeys(used_columns))
    state["last_chart_type"] = "multi"
    state["last_columns_used"] = state["chart_columns_used"]
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()
    state["chart_from_cache"] = False

    params = _chart_params(
        mode="multi",
        chart_type="multi",
        columns=list(dict.fromkeys(preview_cols)),
    )
    payload = {
        "charts": charts,
        "chart_columns_used": state["chart_columns_used"],
        "last_chart_type": "multi",
        "last_columns_used": state["last_columns_used"],
    }
    get_analysis_cache().put(KIND_CHART, fingerprint, payload, params)

    logger.info(
        "Multi visualization generated and cached",
        extra={
            "action": "run_multi_viz",
            "dataset": reference,
            "fingerprint": fingerprint[:16],
            "chart_count": len(charts),
        },
    )
    return state


class VisualizationService:
    """Deterministic visualization generation and caching service."""

    def run(self, state: dict) -> dict:
        try:
            df = state.get("data")
            question = state.get("question") or ""
            question_l = question.lower()
            profile = state.get("dataset_profile", {}) or {}
            last_column = state.get("last_column_used")
            last_columns = list(state.get("last_columns_used") or [])
            if last_column and last_column not in last_columns:
                last_columns = last_columns + [last_column]
            deep_mode = "deeply" in question_l or state.get("last_operation") == "deep_analysis"

            # Clear previous error on new attempt
            state.pop("chart_error", None)

            if df is None:
                state["chart"] = None
                state["chart_columns_used"] = []
                state["chart_error"] = "No data available for visualization."
                state["error_type"] = VISUALIZATION_FAILED
                return state

            if deep_mode:
                return run_multi_viz_agent(state)

            reference = state.get("dataset_url") or state.get("file_path") or state.get("local_path")
            fingerprint = state.get("dataset_fingerprint") or compute_dataset_fingerprint(
                df, reference
            )
            state["dataset_fingerprint"] = fingerprint

            time_cols = list(profile.get("time_columns") or [])
            preferred = detect_requested_chart_type(question)
            # Allow planner/state override
            if state.get("requested_chart_type"):
                preferred = state.get("requested_chart_type")

            # Pre-resolve for cache key stability
            preview = build_chart_safe(
                df,
                question=question,
                preferred_type=preferred,
                time_columns=time_cols,
                last_columns=last_columns,
            )
            spec = preview.get("spec")
            chart_type = (preview.get("chart_type") or (spec.chart_type if spec else "visualization"))
            used_cols = list(spec.used_columns) if spec else []

            params = _chart_params(
                mode="single",
                chart_type=chart_type,
                columns=used_cols,
                question=question,
            )
            cached = get_analysis_cache().get(KIND_CHART, fingerprint, params)
            if cached is not None:
                _apply_cached_charts(state, cached, multi=False)
                state["rows"] = int(df.shape[0])
                state["columns"] = df.columns.tolist()
                logger.info(
                    "Visualization served from durable cache",
                    extra={
                        "action": "run_viz",
                        "dataset": reference,
                        "fingerprint": fingerprint[:16],
                        "chart_type": chart_type,
                        "columns": used_cols,
                    },
                )
                return state

            fig = preview.get("fig")
            validation = preview.get("validation")
            err = preview.get("error")

            if fig is None:
                # Absolute last resort: empty chart metadata without crash
                state["chart"] = None
                state["chart_columns_used"] = []
                state["chart_error"] = (
                    (validation.reason if validation and validation.reason else None)
                    or err
                    or "Could not build a chart for this dataset."
                )
                if validation and validation.recommended_type:
                    state["chart_recommendation"] = validation.recommended_type
                state["error_type"] = VISUALIZATION_FAILED
                logger.warning(
                    "Visualization produced no figure",
                    extra={
                        "action": "run_viz",
                        "error": state["chart_error"],
                        "preferred": preferred,
                    },
                )
                return state

            chart_json = _fig_to_state_json(fig)
            used_cols = list(spec.used_columns) if spec else used_cols
            chart_type = spec.chart_type if spec else chart_type

            state["chart"] = chart_json
            state["chart_columns_used"] = used_cols
            state["last_chart_type"] = chart_type
            state["last_columns_used"] = used_cols
            if used_cols:
                state["last_column_used"] = used_cols[-1]
            state["rows"] = int(df.shape[0])
            state["columns"] = df.columns.tolist()
            state["chart_from_cache"] = False
            state["charts"] = [
                {
                    "type": chart_type,
                    "figure": chart_json,
                    "columns_used": used_cols,
                }
            ]

            # v2 metadata for clients / QA
            if spec is not None:
                state["chart_spec"] = spec.to_dict()
            if validation is not None:
                state["chart_validation"] = {
                    "ok": validation.ok,
                    "reason": validation.reason,
                    "recommended_type": validation.recommended_type,
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                }
                if validation.recommended_type:
                    state["chart_recommendation"] = validation.recommended_type
                if not validation.ok and validation.reason:
                    # Soft notice — chart still produced via redirect/fallback
                    state["chart_notice"] = validation.reason
            if preview.get("fallback_used"):
                state["chart_fallback_used"] = True

            payload = {
                "chart": chart_json,
                "chart_columns_used": used_cols,
                "last_chart_type": chart_type,
                "last_column_used": state.get("last_column_used"),
                "last_columns_used": used_cols,
                "chart_spec": state.get("chart_spec"),
                "chart_validation": state.get("chart_validation"),
                "chart_recommendation": state.get("chart_recommendation"),
            }
            get_analysis_cache().put(KIND_CHART, fingerprint, payload, params)

            logger.info(
                "Visualization generated and cached",
                extra={
                    "action": "run_viz",
                    "dataset": reference,
                    "fingerprint": fingerprint[:16],
                    "chart_type": chart_type,
                    "columns": used_cols,
                    "redirected": bool(spec and spec.redirected),
                    "fallback_used": bool(preview.get("fallback_used")),
                },
            )
            return state
        except Exception as exc:  # noqa: BLE001 — never crash the graph
            state["chart"] = None
            state["chart_columns_used"] = []
            state["chart_error"] = f"Visualization failed: {exc}"
            state["error_type"] = VISUALIZATION_FAILED
            logger.error(
                "Visualization failed",
                extra={"action": "run_viz", "error": str(exc)},
            )
            return state


visualization_service = VisualizationService()


def viz_agent(state: dict) -> dict:
    return visualization_service.run(state)
