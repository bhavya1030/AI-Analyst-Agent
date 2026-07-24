"""Reflection / Self-Correction Agent.

Reviews analytical results before user delivery.
Does not modify Planner, Retrieval, Acquisition, Execution, Viz, or Explainability.
"""

from backend.reflection.exceptions import (
    ReflectionError,
    ReflectionSeverityError,
    ReflectionValidationError,
)
from backend.reflection.models import (
    CorrectedPlan,
    IssueCategory,
    IssueSeverity,
    ReflectionInput,
    ReflectionIssue,
    ReflectionResult,
)
from backend.reflection.prompts import build_reflection_prompt
from backend.reflection.reflection_agent import (
    LLMReflection,
    ReflectionAgent,
    RuleBasedReflection,
    get_reflection_agent,
    reflect_on_analysis,
    reset_reflection_agent,
    set_reflection_agent,
)
from backend.reflection.validator import ReflectionValidator

__all__ = [
    # API
    "reflect_on_analysis",
    "ReflectionAgent",
    "RuleBasedReflection",
    "LLMReflection",
    "get_reflection_agent",
    "set_reflection_agent",
    "reset_reflection_agent",
    "ReflectionValidator",
    "build_reflection_prompt",
    # Models
    "ReflectionInput",
    "ReflectionResult",
    "ReflectionIssue",
    "CorrectedPlan",
    "IssueSeverity",
    "IssueCategory",
    # Exceptions
    "ReflectionError",
    "ReflectionValidationError",
    "ReflectionSeverityError",
]
