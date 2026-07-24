"""Prompts for LLM-based tool selection (optional / future)."""

from __future__ import annotations

import json
from typing import Any, Sequence


def build_tool_selection_prompt(
    question: str,
    tools: Sequence[dict[str, Any]],
    *,
    profile: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Build a strict JSON prompt for selecting analytical tools.

    Used by LLMToolSelector; rule-based selector does not require this.
    """
    catalog = []
    for t in tools:
        catalog.append(
            {
                "tool_id": t.get("tool_id") or t.get("id"),
                "name": t.get("name"),
                "description": t.get("description"),
                "category": t.get("category"),
                "keywords": t.get("keywords") or [],
                "produces_chart": t.get("produces_chart", False),
            }
        )

    profile_summary = _compact_profile(profile)
    context_summary = _compact_context(context)

    payload = {
        "user_question": question,
        "dataset_profile": profile_summary,
        "conversation_context": context_summary,
        "available_tools": catalog,
    }

    return f"""You are an analytics tool selection expert for a data analysis copilot.

Given a user question, optional dataset profile, and conversation context,
select the most appropriate analytical tools from the catalog.

Rules:
- Choose 1 to 6 tools that best answer the question.
- Prefer tools whose requirements match the dataset profile.
- For forecasting questions include forecast and often trend + visualization.
- For relationship questions include correlation and/or regression and scatter_plot.
- For unusual values include outlier_detection and histogram.
- Order tools by recommended execution sequence.
- Return ONLY valid JSON (no markdown).

Return JSON schema:
{{
  "selected_tool_ids": ["tool_id", ...],
  "reason": "<short explanation>",
  "confidence": 0.0
}}

confidence must be between 0 and 1.

Input:
{json.dumps(payload, indent=2, ensure_ascii=False)[:8000]}
"""


def _compact_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    keys = (
        "dataset_type",
        "time_column",
        "entity_column",
        "numeric_metrics",
        "categorical_fields",
        "column_names",
        "row_count",
        "domain",
        "topic_keywords",
    )
    out: dict[str, Any] = {}
    for k in keys:
        if k in profile and profile[k] is not None:
            val = profile[k]
            if isinstance(val, list):
                out[k] = val[:30]
            else:
                out[k] = val
    return out


def _compact_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    out: dict[str, Any] = {}
    for k in (
        "metrics",
        "selected_countries",
        "last_operation",
        "last_intent",
        "last_forecast_target",
        "last_columns",
    ):
        if k in context and context[k] is not None:
            out[k] = context[k]
    filters = context.get("filters")
    if filters:
        if isinstance(filters, list):
            out["filters"] = [
                f.get("label") if isinstance(f, dict) else str(f) for f in filters[:10]
            ]
        else:
            out["filters"] = str(filters)[:200]
    datasets = context.get("active_datasets")
    if datasets and isinstance(datasets, list):
        topics = []
        for d in datasets[:5]:
            if isinstance(d, dict) and d.get("topic"):
                topics.append(d["topic"])
        if topics:
            out["active_topics"] = topics
    return out
