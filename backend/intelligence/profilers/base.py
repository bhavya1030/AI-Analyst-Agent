"""Abstract profiler interface — rule-based today, LLM later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backend.intelligence.models import DatasetProfile


class DatasetProfiler(ABC):
    """Produces a DatasetProfile from a local file path. No charts, no EDA stats."""

    name: str = "base"

    @abstractmethod
    def profile(self, local_path: str | Path) -> DatasetProfile:
        ...
