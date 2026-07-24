"""Models for Dynamic Tool Selection.

Selection metadata only — does not execute analytical tools.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence


class ToolCategory(str, Enum):
    """High-level analytical tool categories."""

    DESCRIPTIVE = "descriptive"
    RELATIONSHIP = "relationship"
    PREDICTIVE = "predictive"
    TIME_SERIES = "time_series"
    DISTRIBUTION = "distribution"
    ANOMALY = "anomaly"
    DIMENSIONALITY = "dimensionality"
    CLUSTERING = "clustering"
    INFERENCE = "inference"
    VISUALIZATION = "visualization"
    GENERAL = "general"


@dataclass
class ToolSpec:
    """
    Declarative description of an analytical tool.

    Used for registration and selection. Does not run the tool.
    """

    tool_id: str
    name: str
    description: str = ""
    category: ToolCategory = ToolCategory.GENERAL
    keywords: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    # Profile signals that boost or are required: time_series, multi_numeric,
    # categorical, entity, multi_metric, large_n, ...
    requires: list[str] = field(default_factory=list)
    prefers: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    produces_chart: bool = False
    # Lower runs earlier in plan when scores tie
    priority: int = 100
    enabled: bool = True
    # True when registered via external plugin API
    is_plugin: bool = False
    version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["category"] = (
            self.category.value if isinstance(self.category, ToolCategory) else self.category
        )
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolSpec":
        data = dict(data or {})
        cat = data.get("category") or ToolCategory.GENERAL
        if isinstance(cat, str):
            try:
                cat = ToolCategory(cat)
            except ValueError:
                cat = ToolCategory.GENERAL
        return cls(
            tool_id=str(data.get("tool_id") or data.get("id") or "").strip(),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            category=cat,
            keywords=[str(k) for k in (data.get("keywords") or [])],
            intents=[str(i) for i in (data.get("intents") or [])],
            requires=[str(r) for r in (data.get("requires") or [])],
            prefers=[str(p) for p in (data.get("prefers") or [])],
            tags=[str(t) for t in (data.get("tags") or [])],
            produces_chart=bool(data.get("produces_chart", False)),
            priority=int(data.get("priority") or 100),
            enabled=bool(data.get("enabled", True)),
            is_plugin=bool(data.get("is_plugin", False)),
            version=str(data.get("version") or "1.0"),
            metadata=dict(data.get("metadata") or {}),
        )


class Tool(ABC):
    """
    Analytical tool interface.

    Implementations provide selection metadata and optional custom scoring.
    Actual analysis execution stays in existing agents/tools (not modified here).
    """

    @property
    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the tool's declarative specification."""

    def score(
        self,
        question: str,
        profile: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> float:
        """
        Relevance score in [0, 1].

        Default implementation is keyword / profile based; plugins may override.
        """
        from backend.tool_selection.selector import default_tool_score

        return default_tool_score(self.spec, question, profile, context)

    def is_applicable(
        self,
        profile: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Hard applicability gate based on required profile signals."""
        from backend.tool_selection.selector import check_requirements

        return check_requirements(self.spec, profile, context)

    def to_dict(self) -> dict[str, Any]:
        return self.spec.to_dict()


@dataclass
class BuiltinTool(Tool):
    """Concrete tool defined entirely by a ToolSpec (no custom execution)."""

    _spec: ToolSpec

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    @classmethod
    def from_spec(cls, spec: ToolSpec) -> "BuiltinTool":
        return cls(_spec=spec)


@dataclass
class SelectedTool:
    """One tool chosen for the execution plan."""

    tool_id: str
    name: str
    category: str
    score: float
    reason: str = ""
    produces_chart: bool = False
    order: int = 0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectedTool":
        data = data or {}
        return cls(
            tool_id=str(data.get("tool_id") or ""),
            name=str(data.get("name") or ""),
            category=str(data.get("category") or ""),
            score=float(data.get("score") or 0.0),
            reason=str(data.get("reason") or ""),
            produces_chart=bool(data.get("produces_chart", False)),
            order=int(data.get("order") or 0),
            tags=[str(t) for t in (data.get("tags") or [])],
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ToolSelectionInput:
    """Inputs for dynamic tool selection."""

    question: str
    profile: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None
    # Optional hard filters
    max_tools: int = 6
    min_score: float = 0.25
    include_visualization: bool = True

    @classmethod
    def from_raw(
        cls,
        question: str,
        profile: Any = None,
        context: Any = None,
        **kwargs: Any,
    ) -> "ToolSelectionInput":
        return cls(
            question=(question or "").strip(),
            profile=_as_profile_dict(profile),
            context=_as_context_dict(context),
            max_tools=int(kwargs.get("max_tools") or 6),
            min_score=float(kwargs.get("min_score") if kwargs.get("min_score") is not None else 0.25),
            include_visualization=bool(kwargs.get("include_visualization", True)),
        )


@dataclass
class ExecutionPlan:
    """
    Ordered analytical tools to run for a question.

    Planner will later consume this; not integrated yet.
    """

    question: str
    selected_tools: list[SelectedTool] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.0
    selector: str = "rule_based"
    profile_signals: list[str] = field(default_factory=list)
    context_hints: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_ids(self) -> list[str]:
        return [t.tool_id for t in self.selected_tools]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "selected_tools": [t.to_dict() for t in self.selected_tools],
            "tool_ids": self.tool_ids,
            "reason": self.reason,
            "confidence": self.confidence,
            "selector": self.selector,
            "profile_signals": list(self.profile_signals),
            "context_hints": dict(self.context_hints),
            "scores": dict(self.scores),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ExecutionPlan":
        data = data or {}
        return cls(
            question=str(data.get("question") or ""),
            selected_tools=[
                SelectedTool.from_dict(t) for t in (data.get("selected_tools") or [])
            ],
            reason=str(data.get("reason") or ""),
            confidence=float(data.get("confidence") or 0.0),
            selector=str(data.get("selector") or "rule_based"),
            profile_signals=list(data.get("profile_signals") or []),
            context_hints=dict(data.get("context_hints") or {}),
            scores={str(k): float(v) for k, v in (data.get("scores") or {}).items()},
            warnings=list(data.get("warnings") or []),
            metadata=dict(data.get("metadata") or {}),
        )


def _as_profile_dict(profile: Any) -> Optional[dict[str, Any]]:
    if profile is None:
        return None
    if isinstance(profile, dict):
        return profile
    if hasattr(profile, "to_dict"):
        return profile.to_dict()
    # DatasetProfile-like object
    out: dict[str, Any] = {}
    for key in (
        "dataset_type",
        "row_count",
        "column_names",
        "column_types",
        "time_column",
        "entity_column",
        "numeric_metrics",
        "categorical_fields",
        "date_range",
        "domain",
        "topic_keywords",
    ):
        if hasattr(profile, key):
            out[key] = getattr(profile, key)
    return out or None


def _as_context_dict(context: Any) -> Optional[dict[str, Any]]:
    if context is None:
        return None
    if isinstance(context, dict):
        return context
    if hasattr(context, "to_dict"):
        return context.to_dict()
    out: dict[str, Any] = {}
    for key in (
        "conversation_id",
        "metrics",
        "selected_countries",
        "filters",
        "last_operation",
        "last_intent",
        "last_forecast_target",
        "last_columns",
        "active_datasets",
    ):
        if hasattr(context, key):
            val = getattr(context, key)
            if hasattr(val, "to_dict"):
                out[key] = val.to_dict()
            elif isinstance(val, list) and val and hasattr(val[0], "to_dict"):
                out[key] = [v.to_dict() for v in val]
            else:
                out[key] = val
    return out or None
