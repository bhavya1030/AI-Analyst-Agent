"""Correlation skill plugin."""

from __future__ import annotations

from typing import Any

from backend.skills.base import Skill


class CorrelationSkill(Skill):
    """Measure relationships between numeric variables."""

    name = "Correlation"
    description = "Measure linear/monotonic relationships between numeric variables."
    version = "1.0.0"
    supported_dataset_types = ("tabular", "time_series")
    supported_questions = (
        "correlation",
        "relationship",
        "related",
        "vs",
        "versus",
        "associated",
    )
    tags = ["stats", "relationship"]
    skill_id = "correlation"

    def execute(self, data: Any = None, **kwargs: Any) -> dict[str, Any]:
        return {
            "skill": self.name,
            "status": "ok",
            "message": "Correlation skill executed (plugin stub).",
        }


SKILL = CorrelationSkill
