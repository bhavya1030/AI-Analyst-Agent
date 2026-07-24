"""Prompts for optional LLM-assisted research planning (future)."""

from __future__ import annotations

import json
from typing import Any


def build_research_plan_prompt(
    question: str,
    *,
    context: dict[str, Any] | None = None,
    known_metrics: list[str] | None = None,
) -> str:
    """
    Build a strict JSON prompt for expanding a broad question into a ResearchPlan.

    Rule-based planner does not require this; LLM path may use it later.
    """
    payload = {
        "user_question": question,
        "conversation_context": _compact_context(context),
        "known_metric_catalog": known_metrics
        or [
            "GDP",
            "Inflation",
            "Population",
            "Exports",
            "Imports",
            "Interest Rates",
            "Unemployment",
            "Investment",
            "Industrial Production",
            "Exchange Rate",
            "Fiscal Deficit",
            "Oil Price",
            "CO2 Emissions",
        ],
    }

    return f"""You are an autonomous research planner for an analytics copilot.

Given a broad analytical question and optional conversation context, produce a
RESEARCH PLAN that lists the datasets needed to answer the question.

Do NOT retrieve or analyze data. Only plan.

Support research types:
- comparison
- root_cause
- trend
- forecasting
- correlation
- impact
- benchmarking
- exploration

Rules:
- Infer related metrics the user did not name when needed for root-cause / impact.
- Mark datasets mandatory vs optional.
- Assign priority (critical|high|medium|low) and depends_on links.
- Include analysis goals and expected outputs.
- Prefer 2–8 datasets.
- Return ONLY valid JSON (no markdown).

Return JSON schema:
{{
  "objective_type": "root_cause",
  "objective_summary": "<one sentence>",
  "primary_metric": "GDP",
  "entities": ["India"],
  "datasets": [
    {{
      "topic": "India GDP",
      "reason": "...",
      "priority": "critical",
      "necessity": "mandatory",
      "role": "primary_metric",
      "depends_on": []
    }}
  ],
  "analysis_goals": [
    {{"goal_id": "g1", "description": "...", "goal_type": "trend", "target_datasets": ["India GDP"]}}
  ],
  "expected_outputs": [
    {{"output_type": "insight", "description": "..."}}
  ],
  "confidence": 0.0
}}

Input:
{json.dumps(payload, indent=2, ensure_ascii=False)[:7000]}
"""


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
        "entities",
    ):
        if context.get(k) is not None:
            out[k] = context[k]
    datasets = context.get("active_datasets")
    if isinstance(datasets, list):
        topics = []
        for d in datasets[:5]:
            if isinstance(d, dict) and d.get("topic"):
                topics.append(d["topic"])
        if topics:
            out["active_topics"] = topics
    return out
