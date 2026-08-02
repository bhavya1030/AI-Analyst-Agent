"""Response builder — formats LangGraph results into stable HTTP response dicts.

Extracted verbatim from backend/main.py (_stable_response).
Logic is identical; only location changed.
"""

from __future__ import annotations

from backend.utils.json_safe import sanitize_for_json


def build_stable_response(
    result: dict,
    question: str | None = None,
    timings: dict | None = None,
) -> dict:
    """Format a raw LangGraph result dict into a stable HTTP response dict.

    Mirrors the logic of the former ``_stable_response`` in main.py exactly.
    """
    dataset_profile = result.get("dataset_profile") or {}
    charts = result.get("charts") or []
    if not charts and result.get("chart") is not None:
        charts = [result.get("chart")]

    # Merge stage timings from graph state + request timer
    from backend.production.pipeline_timing import (
        extract_timings_from_state,
        get_timer,
        merge_timings,
    )

    state_timings = extract_timings_from_state(result if isinstance(result, dict) else {})
    timer = get_timer()
    timer_timings = timer.as_dict() if timer is not None else {}
    merged = merge_timings(
        state_timings,
        timer_timings,
        timings if isinstance(timings, dict) else None,
    )
    if "total" not in merged and timer is not None:
        merged["total"] = timer.as_dict().get("total", 0)

    payload = {
        "question": question or "",
        "answer": result.get("answer") or "",
        "dataset_summary": dataset_profile,
        "dataset_topic": result.get("dataset_topic") or result.get("dataset_name") or "",
        "dataset_name": (
            result.get("dataset_name")
            or result.get("dataset_title")
            or (result.get("dataset_metadata") or {}).get("title")
            or result.get("dataset_topic")
            or ""
        ),
        "charts": charts,
        "generated_charts": charts,
        "chart": result.get("chart") or {},
        "chart_columns_used": result.get("chart_columns_used") or [],
        "forecast": result.get("forecast") or [],
        "forecast_chart": result.get("forecast_chart") or {},
        "forecast_error": result.get("forecast_error") or "",
        "forecast_model": result.get("forecast_model") or "",
        "forecast_partial": bool(result.get("forecast_partial")),
        "forecast_from_cache": bool(result.get("forecast_from_cache")),
        "forecast_timings": result.get("forecast_timings") or {},
        "forecast_explanation": result.get("forecast_explanation") or "",
        "forecast_suggested_retry": result.get("forecast_suggested_retry") or "",
        "chart_error": result.get("chart_error") or "",
        "detected_patterns": result.get("detected_patterns") or [],
        "insights": result.get("insights") or [],
        "recommended_next_steps": result.get("recommended_next_steps") or [],
        "dataset_explanation": result.get("dataset_explanation") or [],
        "related_datasets": result.get("related_datasets") or [],
        "chart_explanation": result.get("chart_explanation") or "",
        "hypotheses": result.get("hypotheses") or [],
        "dataset_url": result.get("dataset_url") or "",
        "rows": result.get("rows") or 0,
        "columns": result.get("columns") or [],
        "error": result.get("error") or "",
        "error_type": result.get("error_type") or "",
        # Open-world acquisition: open data / upload / connect sources
        "needs_user_data": bool(result.get("needs_user_data")),
        "data_acquisition_options": result.get("data_acquisition_options") or [],
        "dataset_discovery": result.get("dataset_discovery") or {},
        "search_queries": result.get("search_queries") or [],
        "source": result.get("source") or result.get("dataset_source") or "",
        "product_promise": (
            "Ask about any topic. We'll find open data when we can, "
            "use your files when you have them, or connect your sources — "
            "then analyze, chart, and forecast."
        ),
        "dataset_learned": bool(result.get("dataset_learned")),
        "learned_aliases": result.get("learned_aliases") or [],
        "topic_via_llm": bool(result.get("topic_via_llm")),
        "timings": merged,
    }
    return sanitize_for_json(payload)
