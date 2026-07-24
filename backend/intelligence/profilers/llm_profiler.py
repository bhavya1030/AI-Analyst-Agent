"""LLM-based profiler placeholder.

Future: use Ollama / remote LLM to refine domain, entity roles, and dataset_type
after a rule-based pass (or instead of it). Not used by default.
"""

from __future__ import annotations

from pathlib import Path

from backend.intelligence.exceptions import IntelligenceValidationError
from backend.intelligence.models import DatasetProfile
from backend.intelligence.profilers.base import DatasetProfiler
from backend.intelligence.profilers.rule_based import RuleBasedProfiler


class LLMProfiler(DatasetProfiler):
    """
    Placeholder implementation.

    Currently delegates to RuleBasedProfiler so the swap-point is real.
    Later: call Ollama with column names + samples and merge into DatasetProfile.
    """

    name = "llm"

    def __init__(self, fallback: DatasetProfiler | None = None):
        self._fallback = fallback or RuleBasedProfiler()

    def profile(self, local_path: str | Path) -> DatasetProfile:
        if not Path(local_path).is_file():
            raise IntelligenceValidationError(f"Dataset file not found: {local_path}")

        # Structural base from rules (required for types/columns)
        base = self._fallback.profile(local_path)

        # Future LLM enrichment hook — intentionally no network/LLM call yet.
        base.profiler = self.name
        base.notes = list(base.notes or [])
        base.notes.append(
            "LLM profiler placeholder: used rule-based structure; LLM enrichment not enabled."
        )
        return base
