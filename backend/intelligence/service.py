"""Dataset Intelligence Service — structural profiling only.

Not EDA: no summary statistics, correlations, charts, or cleaning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.core.logger import get_logger
from backend.intelligence.exceptions import IntelligenceValidationError
from backend.intelligence.models import DatasetProfile
from backend.intelligence.profilers.base import DatasetProfiler
from backend.intelligence.profilers.llm_profiler import LLMProfiler
from backend.intelligence.profilers.rule_based import RuleBasedProfiler

logger = get_logger(__name__)

_default_profiler: DatasetProfiler | None = None


def get_default_profiler() -> DatasetProfiler:
    global _default_profiler
    if _default_profiler is None:
        _default_profiler = RuleBasedProfiler()
    return _default_profiler


def set_default_profiler(profiler: DatasetProfiler) -> None:
    """Swap rule-based profiler for LLMProfiler (or custom) with no service changes."""
    global _default_profiler
    _default_profiler = profiler


class DatasetIntelligenceService:
    """High-level API for dataset structure intelligence."""

    def __init__(self, profiler: DatasetProfiler | None = None):
        self._profiler = profiler or get_default_profiler()

    def profile_dataset(self, local_path: str | Path) -> DatasetProfile:
        path = Path(local_path).expanduser() if local_path else None
        if path is None or not str(local_path).strip():
            raise IntelligenceValidationError("local_path is required")
        if not path.is_file():
            raise IntelligenceValidationError(f"Dataset file not found: {local_path}")

        profile = self._profiler.profile(path)
        logger.info(
            "Dataset intelligence complete",
            extra={
                "path": str(path),
                "type": profile.dataset_type,
                "domain": profile.domain,
                "profiler": profile.profiler,
            },
        )
        return profile


def profile_dataset(
    local_path: str | Path,
    *,
    use_llm: bool = False,
) -> DatasetProfile:
    """
    Module-level entrypoint.

    use_llm=True selects LLMProfiler (currently rule-based with LLM hook notes).
    """
    if use_llm:
        service = DatasetIntelligenceService(profiler=LLMProfiler())
    else:
        service = DatasetIntelligenceService()
    return service.profile_dataset(local_path)
