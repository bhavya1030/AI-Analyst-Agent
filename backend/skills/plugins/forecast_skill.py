"""Forecast skill plugin."""

from __future__ import annotations

from typing import Any

from backend.skills.base import Skill


class ForecastSkill(Skill):
    """Forecast future values of a time-dependent metric."""

    name = "Forecast"
    description = "Forecast future values of a time-dependent metric."
    version = "1.0.0"
    dependencies: list[str] = []
    supported_dataset_types = ("time_series", "tabular")
    supported_questions = (
        "forecast",
        "predict",
        "prediction",
        "next years",
        "future",
        "projection",
    )
    tags = ["forecast", "time"]
    skill_id = "forecast"

    def execute(self, data: Any = None, horizon: int = 5, **kwargs: Any) -> dict[str, Any]:
        return {
            "skill": self.name,
            "horizon": horizon,
            "status": "ok",
            "message": "Forecast skill executed (plugin stub).",
            "rows": getattr(data, "__len__", lambda: None)(),
        }


# Explicit export for loader
SKILL = ForecastSkill
