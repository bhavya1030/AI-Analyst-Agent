"""Prompts for LLMDatasetSelector (future use)."""

from __future__ import annotations

from typing import Any


def build_selection_prompt(question: str, candidates: list[dict[str, Any]]) -> str:
    """Build a strict JSON-selection prompt for an LLM."""
    import json

    payload = {
        "user_question": question,
        "candidates": candidates,
        "instructions": (
            "Pick the single best dataset for answering the user question. "
            "Prefer loadable tabular sources that match the topic. "
            "Return ONLY JSON."
        ),
    }
    return f"""You are a dataset selection expert for an analytics copilot.

Given a user question and candidate datasets, choose the BEST dataset.

Return ONLY valid JSON:
{{
  "best_candidate_id": "<id>",
  "reason": "<short explanation>",
  "confidence": 0.0
}}

confidence must be between 0 and 1.

Input:
{json.dumps(payload, indent=2, ensure_ascii=False)[:6000]}
"""
