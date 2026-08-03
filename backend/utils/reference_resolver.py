"""Phase 4 — LLM Reference Resolution.

Resolves conversational follow-ups, ambiguous pronouns ('it', 'this', 'that', 'those columns'),
and chart references into fully explicit query strings before passing to Planner.
"""

from __future__ import annotations

import re
from typing import Any

from backend.config import settings
from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm

logger = get_logger(__name__)


def resolve_question_references(
    question: str,
    *,
    dataset_name: str | None = None,
    dataset_topic: str | None = None,
    last_chart: str | None = None,
    last_chart_type: str | None = None,
    last_operation: str | None = None,
    last_column: str | None = None,
    columns: list[str] | None = None,
    has_active_dataset: bool = False,
) -> str:
    """
    Phase 4 — Resolves ambiguous conversational references ('it', 'this', 'those columns')
    into fully explicit question strings before passing to Planner.
    """
    q = (question or "").strip()
    if not q:
        return q

    ds_label = (dataset_name or dataset_topic or "").strip()
    if not ds_label and has_active_dataset:
        ds_label = "active dataset"

    lowered = q.lower()

    # 1. Visual / Chart reference resolution
    chart_label = (last_chart or "").strip()
    if not chart_label:
        if last_operation and "correlation" in last_operation.lower():
            chart_label = "correlation matrix chart"
        elif last_chart_type and last_column:
            chart_label = f"{last_chart_type} of {last_column} chart"
        elif last_chart_type:
            chart_label = f"{last_chart_type} chart"

    is_visual_ref = any(
        p in lowered
        for p in (
            "explain this",
            "explain that",
            "what does this show",
            "what does this mean",
            "interpret this",
            "explain graph",
            "explain plot",
        )
    )
    if is_visual_ref and chart_label:
        clean_label = chart_label
        if not clean_label.lower().endswith("chart") and not clean_label.lower().endswith("matrix"):
            clean_label = f"{clean_label} chart"
        return f"Explain the {clean_label}"

    # 2. Active dataset reference resolution
    if ds_label:
        if lowered in {"describe it", "describe this", "describe the dataset"}:
            return f"Describe the dataset {ds_label}"

        if lowered in {"show missing values", "missing values", "null values", "show nulls"}:
            return f"Show missing values in dataset {ds_label}"

        if (
            lowered.startswith("average ")
            or lowered.startswith("mean ")
            or lowered.startswith("max ")
            or lowered.startswith("min ")
            or lowered.startswith("summary ")
        ):
            if " in dataset " not in lowered and " in " not in lowered:
                return f"Calculate {q.strip().lower()} in dataset {ds_label}"

        if re.search(r"\b(it|this|that|the dataset)\b", lowered):
            resolved = re.sub(
                r"\b(it|this|that|the dataset)\b",
                f"dataset {ds_label}",
                q,
                flags=re.IGNORECASE,
            )
            return resolved

    # Opt-in LLM resolution for complex contextual references
    if has_active_dataset and bool(getattr(settings, "USE_LLM_REFERENCE_RESOLVER", False)):
        try:
            resolved_llm = _resolve_via_llm(
                q,
                dataset_name=ds_label,
                last_chart=chart_label,
                last_operation=last_operation,
            )
            if resolved_llm:
                return resolved_llm
        except Exception as exc:
            logger.warning("LLM reference resolution failed", extra={"error": str(exc)})

    return q


def _resolve_via_llm(
    question: str,
    *,
    dataset_name: str | None = None,
    last_chart: str | None = None,
    last_operation: str | None = None,
) -> str | None:
    prompt = f"""You are a conversational reference resolver for a Data Analyst Agent.
Rewrite the user question into a fully explicit, unambiguous query.

Context:
- Active Dataset: {dataset_name or 'None'}
- Previous Chart: {last_chart or 'None'}
- Previous Operation: {last_operation or 'None'}

User Question: {question}

Return ONLY the rewritten, explicit query string:"""

    logger.info("LLM REFERENCE RESOLVER INVOKED", extra={"question": question})
    response = invoke_llm(prompt)
    if response and isinstance(response, str):
        cleaned = response.strip().strip('"').strip("'")
        if cleaned:
            return cleaned
    return None
