"""Models for Reflection / Self-Correction Agent.

Reviews analytical outputs before user delivery. Does not re-run analysis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class IssueSeverity(str, Enum):
    """Severity of a reflection finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IssueCategory(str, Enum):
    """Which quality dimension failed."""

    DATASET = "dataset_correctness"
    REASONING = "reasoning_consistency"
    CONFIDENCE = "confidence_validation"
    CITATIONS = "missing_citations"
    VISUALIZATION = "visualization_review"
    JOIN = "join_validation"
    STATISTICAL = "statistical_sanity"
    HALLUCINATION = "hallucination_detection"
    GENERAL = "general"


@dataclass
class ReflectionIssue:
    """One detected problem in the analytical package."""

    code: str
    message: str
    category: IssueCategory = IssueCategory.GENERAL
    severity: IssueSeverity = IssueSeverity.WARNING
    evidence: str = ""
    recommendation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "category": self.category.value
            if isinstance(self.category, IssueCategory)
            else self.category,
            "severity": self.severity.value
            if isinstance(self.severity, IssueSeverity)
            else self.severity,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReflectionIssue":
        data = data or {}
        cat = data.get("category") or IssueCategory.GENERAL
        if isinstance(cat, str):
            try:
                cat = IssueCategory(cat)
            except ValueError:
                cat = IssueCategory.GENERAL
        sev = data.get("severity") or IssueSeverity.WARNING
        if isinstance(sev, str):
            try:
                sev = IssueSeverity(sev)
            except ValueError:
                sev = IssueSeverity.WARNING
        return cls(
            code=str(data.get("code") or "unknown"),
            message=str(data.get("message") or ""),
            category=cat,
            severity=sev,
            evidence=str(data.get("evidence") or ""),
            recommendation=str(data.get("recommendation") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class CorrectedPlan:
    """
    Suggested re-execution adjustments when severe issues are found.

    Not executed here — returned for Planner / graph to act on later.
    """

    should_rerun: bool = False
    reason: str = ""
    suggested_tools: list[str] = field(default_factory=list)
    suggested_datasets: list[str] = field(default_factory=list)
    suggested_chart_types: list[str] = field(default_factory=list)
    join_notes: list[str] = field(default_factory=list)
    drop_claims: list[str] = field(default_factory=list)
    require_citations: bool = False
    lower_confidence: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CorrectedPlan":
        data = data or {}
        return cls(
            should_rerun=bool(data.get("should_rerun")),
            reason=str(data.get("reason") or ""),
            suggested_tools=[str(t) for t in (data.get("suggested_tools") or [])],
            suggested_datasets=[str(d) for d in (data.get("suggested_datasets") or [])],
            suggested_chart_types=[str(c) for c in (data.get("suggested_chart_types") or [])],
            join_notes=[str(n) for n in (data.get("join_notes") or [])],
            drop_claims=[str(c) for c in (data.get("drop_claims") or [])],
            require_citations=bool(data.get("require_citations")),
            lower_confidence=bool(data.get("lower_confidence")),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ReflectionInput:
    """Bundle of pipeline artifacts reviewed by the reflection agent."""

    question: str = ""
    conversation_context: Optional[dict[str, Any]] = None
    execution_plan: Optional[dict[str, Any]] = None
    analysis_result: Optional[dict[str, Any]] = None
    explanation_result: Optional[dict[str, Any]] = None
    charts: list[dict[str, Any]] = field(default_factory=list)
    datasets_used: list[dict[str, Any]] = field(default_factory=list)
    join_plan: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        *,
        question: str = "",
        conversation_context: Any = None,
        execution_plan: Any = None,
        analysis_result: Any = None,
        explanation_result: Any = None,
        charts: Any = None,
        datasets_used: Any = None,
        join_plan: Any = None,
        metadata: Any = None,
        **kwargs: Any,
    ) -> "ReflectionInput":
        return cls(
            question=(question or kwargs.get("question") or "").strip(),
            conversation_context=_as_dict(conversation_context),
            execution_plan=_as_dict(execution_plan),
            analysis_result=_as_dict(analysis_result),
            explanation_result=_as_dict(explanation_result),
            charts=_as_list_of_dicts(charts),
            datasets_used=_as_list_of_dicts(datasets_used),
            join_plan=_as_dict(join_plan),
            metadata=dict(metadata or {}),
        )


@dataclass
class ReflectionResult:
    """
    Outcome of self-correction review.

    approved=True  → original result may be returned as-is
    warnings only  → attach issues, keep result
    severe issues  → corrected_plan.should_rerun recommended
    """

    approved: bool
    issues: list[ReflectionIssue] = field(default_factory=list)
    severity: IssueSeverity = IssueSeverity.INFO  # max severity seen
    recommendations: list[str] = field(default_factory=list)
    corrected_plan: Optional[CorrectedPlan] = None
    confidence_adjustment: float = 0.0  # delta to apply (e.g. -0.2)
    original_confidence: Optional[float] = None
    adjusted_confidence: Optional[float] = None
    summary: str = ""
    reflector: str = "rule_based"
    question: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_warnings(self) -> bool:
        return any(
            i.severity in {IssueSeverity.WARNING, IssueSeverity.ERROR, IssueSeverity.CRITICAL}
            for i in self.issues
        )

    @property
    def has_severe_issues(self) -> bool:
        return any(
            i.severity in {IssueSeverity.ERROR, IssueSeverity.CRITICAL} for i in self.issues
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "issues": [i.to_dict() for i in self.issues],
            "severity": self.severity.value
            if isinstance(self.severity, IssueSeverity)
            else self.severity,
            "recommendations": list(self.recommendations),
            "corrected_plan": self.corrected_plan.to_dict() if self.corrected_plan else None,
            "confidence_adjustment": self.confidence_adjustment,
            "original_confidence": self.original_confidence,
            "adjusted_confidence": self.adjusted_confidence,
            "summary": self.summary,
            "reflector": self.reflector,
            "question": self.question,
            "has_warnings": self.has_warnings,
            "has_severe_issues": self.has_severe_issues,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReflectionResult":
        data = data or {}
        sev = data.get("severity") or IssueSeverity.INFO
        if isinstance(sev, str):
            try:
                sev = IssueSeverity(sev)
            except ValueError:
                sev = IssueSeverity.INFO
        plan = data.get("corrected_plan")
        return cls(
            approved=bool(data.get("approved", True)),
            issues=[ReflectionIssue.from_dict(i) for i in (data.get("issues") or [])],
            severity=sev,
            recommendations=list(data.get("recommendations") or []),
            corrected_plan=CorrectedPlan.from_dict(plan) if plan else None,
            confidence_adjustment=float(data.get("confidence_adjustment") or 0.0),
            original_confidence=_as_float(data.get("original_confidence")),
            adjusted_confidence=_as_float(data.get("adjusted_confidence")),
            summary=str(data.get("summary") or ""),
            reflector=str(data.get("reflector") or "rule_based"),
            question=str(data.get("question") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


def _as_dict(value: Any) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except TypeError:
            return value.to_dict()
    if hasattr(value, "__dict__"):
        return {
            k: v
            for k, v in vars(value).items()
            if not k.startswith("_") and type(v).__name__ not in {"DataFrame", "Series"}
        }
    return {"value": str(value)}


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, (list, tuple)):
        d = _as_dict(value)
        return [d] if d else []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
        elif hasattr(item, "to_dict"):
            out.append(item.to_dict())
        elif item is not None:
            out.append({"value": str(item)})
    return out


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
