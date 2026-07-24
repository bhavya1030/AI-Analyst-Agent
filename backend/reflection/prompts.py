"""Prompts for optional LLM-based reflection (future)."""

from __future__ import annotations

import json
from typing import Any


def build_reflection_prompt(payload: dict[str, Any]) -> str:
    """
    Strict JSON prompt for LLMReflection.

    RuleBasedReflection does not use this.
    """
    return f"""You are a quality-assurance reflection agent for an analytics copilot.

Review the analysis package and detect:
1. Inappropriate datasets
2. Unsupported conclusions
3. Over-confident claims
4. Missing citations
5. Poor chart choices
6. Suspicious joins
7. Statistically impossible claims
8. Hallucinated / unsupported statements

Return ONLY valid JSON:
{{
  "approved": true,
  "issues": [
    {{
      "code": "short_code",
      "message": "what is wrong",
      "category": "dataset_correctness|reasoning_consistency|confidence_validation|missing_citations|visualization_review|join_validation|statistical_sanity|hallucination_detection|general",
      "severity": "info|warning|error|critical",
      "evidence": "snippet or reason",
      "recommendation": "how to fix"
    }}
  ],
  "recommendations": ["..."],
  "confidence_adjustment": -0.1,
  "should_rerun": false,
  "corrected_plan": {{
    "suggested_tools": [],
    "suggested_datasets": [],
    "suggested_chart_types": [],
    "join_notes": [],
    "drop_claims": []
  }},
  "summary": "one paragraph"
}}

Rules:
- Prefer WARNING over ERROR unless conclusions are clearly unsafe.
- CRITICAL only for contradictory or impossible claims presented as fact.
- confidence_adjustment is a delta in [-0.5, 0.1].
- Do not invent datasets that were not provided.

Input package:
{json.dumps(payload, indent=2, ensure_ascii=False)[:9000]}
"""
