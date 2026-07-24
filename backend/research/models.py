"""Models for Autonomous Research Planning.

Planning only — no retrieval, acquisition, or analysis execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ResearchObjectiveType(str, Enum):
    """High-level research modes the agent can plan for."""

    COMPARISON = "comparison"
    ROOT_CAUSE = "root_cause"
    TREND = "trend"
    FORECASTING = "forecasting"
    CORRELATION = "correlation"
    IMPACT = "impact"
    BENCHMARKING = "benchmarking"
    EXPLORATION = "exploration"
    MULTI_METRIC = "multi_metric"


class DatasetPriority(str, Enum):
    CRITICAL = "critical"  # must have
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DatasetNecessity(str, Enum):
    MANDATORY = "mandatory"
    OPTIONAL = "optional"


@dataclass
class DatasetRequirement:
    """One dataset the research plan needs (topic label only — not retrieved)."""

    topic: str
    reason: str = ""
    priority: DatasetPriority = DatasetPriority.MEDIUM
    necessity: DatasetNecessity = DatasetNecessity.OPTIONAL
    # Topics that should be available before this one is most useful
    depends_on: list[str] = field(default_factory=list)
    # Role in research: primary_metric | driver | control | benchmark | context
    role: str = "context"
    entities: list[str] = field(default_factory=list)  # e.g. ["India"]
    order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "reason": self.reason,
            "priority": self.priority.value
            if isinstance(self.priority, DatasetPriority)
            else self.priority,
            "necessity": self.necessity.value
            if isinstance(self.necessity, DatasetNecessity)
            else self.necessity,
            "depends_on": list(self.depends_on),
            "role": self.role,
            "entities": list(self.entities),
            "order": self.order,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DatasetRequirement":
        data = data or {}
        pr = data.get("priority") or DatasetPriority.MEDIUM
        if isinstance(pr, str):
            try:
                pr = DatasetPriority(pr)
            except ValueError:
                pr = DatasetPriority.MEDIUM
        nec = data.get("necessity") or DatasetNecessity.OPTIONAL
        if isinstance(nec, str):
            try:
                nec = DatasetNecessity(nec)
            except ValueError:
                nec = DatasetNecessity.OPTIONAL
        return cls(
            topic=str(data.get("topic") or "").strip(),
            reason=str(data.get("reason") or ""),
            priority=pr,
            necessity=nec,
            depends_on=[str(d) for d in (data.get("depends_on") or [])],
            role=str(data.get("role") or "context"),
            entities=[str(e) for e in (data.get("entities") or [])],
            order=int(data.get("order") or 0),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class AnalysisGoal:
    """A concrete analysis goal within the research plan."""

    goal_id: str
    description: str
    goal_type: str = ""  # trend | correlation | compare | forecast | root_cause | ...
    target_datasets: list[str] = field(default_factory=list)
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AnalysisGoal":
        data = data or {}
        return cls(
            goal_id=str(data.get("goal_id") or ""),
            description=str(data.get("description") or ""),
            goal_type=str(data.get("goal_type") or ""),
            target_datasets=[str(t) for t in (data.get("target_datasets") or [])],
            priority=int(data.get("priority") or 100),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ExpectedOutput:
    """What the research should produce (charts, insights, tables — not executed here)."""

    output_type: str  # insight | chart | comparison_table | forecast | report_section
    description: str = ""
    related_goals: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ExpectedOutput":
        data = data or {}
        return cls(
            output_type=str(data.get("output_type") or ""),
            description=str(data.get("description") or ""),
            related_goals=[str(g) for g in (data.get("related_goals") or [])],
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ResearchObjective:
    """Interpreted research objective derived from the user question."""

    objective_type: ResearchObjectiveType
    summary: str = ""
    primary_metric: str = ""
    entities: list[str] = field(default_factory=list)
    secondary_metrics: list[str] = field(default_factory=list)
    time_horizon: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_type": (
                self.objective_type.value
                if isinstance(self.objective_type, ResearchObjectiveType)
                else self.objective_type
            ),
            "summary": self.summary,
            "primary_metric": self.primary_metric,
            "entities": list(self.entities),
            "secondary_metrics": list(self.secondary_metrics),
            "time_horizon": self.time_horizon,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ResearchObjective":
        data = data or {}
        ot = data.get("objective_type") or ResearchObjectiveType.EXPLORATION
        if isinstance(ot, str):
            try:
                ot = ResearchObjectiveType(ot)
            except ValueError:
                ot = ResearchObjectiveType.EXPLORATION
        return cls(
            objective_type=ot,
            summary=str(data.get("summary") or ""),
            primary_metric=str(data.get("primary_metric") or ""),
            entities=[str(e) for e in (data.get("entities") or [])],
            secondary_metrics=[str(m) for m in (data.get("secondary_metrics") or [])],
            time_horizon=data.get("time_horizon"),
            notes=list(data.get("notes") or []),
        )


@dataclass
class ResearchPlan:
    """
    Complete research plan produced by the Autonomous Research Agent.

    Does not retrieve data or run analysis.
    """

    question: str
    objective: ResearchObjective
    required_datasets: list[DatasetRequirement] = field(default_factory=list)
    analysis_goals: list[AnalysisGoal] = field(default_factory=list)
    expected_outputs: list[ExpectedOutput] = field(default_factory=list)
    # Explicit dependency edges: {"from": topic_a, "to": topic_b} means b depends on a
    dependencies: list[dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0
    planner: str = "rule_based"
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    context_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def mandatory_topics(self) -> list[str]:
        return [
            d.topic
            for d in self.required_datasets
            if d.necessity == DatasetNecessity.MANDATORY
        ]

    @property
    def optional_topics(self) -> list[str]:
        return [
            d.topic
            for d in self.required_datasets
            if d.necessity == DatasetNecessity.OPTIONAL
        ]

    @property
    def topics(self) -> list[str]:
        return [d.topic for d in self.required_datasets]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "objective": self.objective.to_dict(),
            "required_datasets": [d.to_dict() for d in self.required_datasets],
            "analysis_goals": [g.to_dict() for g in self.analysis_goals],
            "expected_outputs": [o.to_dict() for o in self.expected_outputs],
            "dependencies": list(self.dependencies),
            "mandatory_topics": self.mandatory_topics,
            "optional_topics": self.optional_topics,
            "topics": self.topics,
            "confidence": self.confidence,
            "planner": self.planner,
            "warnings": list(self.warnings),
            "notes": list(self.notes),
            "context_used": self.context_used,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ResearchPlan":
        data = data or {}
        obj = data.get("objective") or {}
        return cls(
            question=str(data.get("question") or ""),
            objective=ResearchObjective.from_dict(obj if isinstance(obj, dict) else {}),
            required_datasets=[
                DatasetRequirement.from_dict(d)
                for d in (data.get("required_datasets") or [])
            ],
            analysis_goals=[
                AnalysisGoal.from_dict(g) for g in (data.get("analysis_goals") or [])
            ],
            expected_outputs=[
                ExpectedOutput.from_dict(o) for o in (data.get("expected_outputs") or [])
            ],
            dependencies=list(data.get("dependencies") or []),
            confidence=float(data.get("confidence") or 0.0),
            planner=str(data.get("planner") or "rule_based"),
            warnings=list(data.get("warnings") or []),
            notes=list(data.get("notes") or []),
            context_used=bool(data.get("context_used")),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ResearchInput:
    """Input contract for the research agent."""

    question: str
    context: Optional[dict[str, Any]] = None
    conversation_id: Optional[str] = None
    max_datasets: int = 8

    @classmethod
    def from_raw(
        cls,
        question: str,
        context: Any = None,
        **kwargs: Any,
    ) -> "ResearchInput":
        ctx = _as_context_dict(context)
        return cls(
            question=(question or "").strip(),
            context=ctx,
            conversation_id=kwargs.get("conversation_id")
            or (ctx or {}).get("conversation_id"),
            max_datasets=int(kwargs.get("max_datasets") or 8),
        )


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
        "entities",
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
