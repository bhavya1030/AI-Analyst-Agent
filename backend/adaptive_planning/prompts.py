"""Prompts for optional LLM-assisted replan suggestions (future)."""

from __future__ import annotations

import json
from typing import Any


def build_replan_prompt(
    question: str,
    *,
    completed_steps: list[dict[str, Any]],
    remaining_steps: list[dict[str, Any]],
    observation: dict[str, Any],
    trigger: str,
    reason: str,
) -> str:
    """
    JSON prompt for future LLM replan generation.

    Rule-based AdaptivePlanner does not require this.
    """
    payload = {
        "user_question": question,
        "trigger": trigger,
        "reason": reason,
        "last_observation": observation,
        "completed_steps": completed_steps,
        "remaining_steps": remaining_steps,
    }
    return f"""You are an adaptive planning controller for an analytics copilot.

After a step observation, decide how to revise the REMAINING plan.

Triggers may include: dataset_not_found, low_confidence, unexpected_schema,
poor_join, empty_result, user_interruption, new_follow_up, step_failure.

Return ONLY valid JSON:
{{
  "need_replan": true,
  "reason": "...",
  "replace_remaining": true,
  "new_steps": [
    {{
      "step_id": "s_new_1",
      "name": "Retrieve alternative dataset",
      "step_type": "retrieve",
      "params": {{}}
    }}
  ],
  "retry_step_id": null
}}

Rules:
- Prefer minimal changes.
- On dataset_not_found: suggest alternate retrieve/search steps.
- On poor_join: suggest schema alignment then outer/concat join.
- On low_confidence: add reflect/explain or gather more data.
- On new_follow_up: append steps for the follow-up intent.
- Do not re-run already completed successful steps unless required.

Input:
{json.dumps(payload, indent=2, ensure_ascii=False)[:7000]}
"""
