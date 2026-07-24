"""Models for the Explainability Layer.

Structured reasoning about how an analytical answer was produced.
Does not run analysis, retrieval, or visualization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ExplanationStyle(str, Enum):
    """Verbosity / audience for generated explanations."""

    SHORT = "short"
    DETAILED = "detailed"
    TECHNICAL = "technical"


@dataclass
class DatasetCitation:
    """Citation to dataset metadata used in the analysis."""

    topic: str = ""
    dataset_id: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    local_path: Optional[str] = None
    provider: Optional[str] = None
    columns: list[str] = field(default_factory=list)
    row_count: Optional[int] = None
    citation_label: str = ""  # e.g. "[1] World Bank — India GDP"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DatasetCitation":
        data = data or {}
        return cls(
            topic=str(data.get("topic") or data.get("title") or ""),
            dataset_id=data.get("dataset_id") or data.get("registry_id") or data.get("id"),
            source=data.get("source"),
            source_url=data.get("source_url")
            or data.get("download_url")
            or data.get("url"),
            local_path=data.get("local_path"),
            provider=data.get("provider"),
            columns=[str(c) for c in (data.get("columns") or data.get("column_names") or [])],
            row_count=_as_int(data.get("row_count")),
            citation_label=str(data.get("citation_label") or ""),
            metadata={
                k: v
                for k, v in data.items()
                if k
                not in {
                    "topic",
                    "title",
                    "dataset_id",
                    "registry_id",
                    "id",
                    "source",
                    "source_url",
                    "download_url",
                    "url",
                    "local_path",
                    "provider",
                    "columns",
                    "column_names",
                    "row_count",
                    "citation_label",
                }
            },
        )


@dataclass
class JoinExplanation:
    """How datasets were joined / merged."""

    strategy: str = ""
    join_keys: list[str] = field(default_factory=list)
    datasets_merged: int = 0
    notes: list[str] = field(default_factory=list)
    schema_alignment: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "JoinExplanation":
        data = data or {}
        return cls(
            strategy=str(data.get("strategy") or data.get("join_strategy") or ""),
            join_keys=[str(k) for k in (data.get("join_keys") or [])],
            datasets_merged=int(data.get("datasets_merged") or 0),
            notes=[str(n) for n in (data.get("notes") or data.get("warnings") or [])],
            schema_alignment=data.get("schema_alignment"),
        )


@dataclass
class ToolStepExplanation:
    """One analytical tool that contributed to the result."""

    tool_id: str = ""
    name: str = ""
    category: str = ""
    reason: str = ""
    order: int = 0
    produces_chart: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ToolStepExplanation":
        data = data or {}
        return cls(
            tool_id=str(data.get("tool_id") or data.get("id") or ""),
            name=str(data.get("name") or ""),
            category=str(data.get("category") or ""),
            reason=str(data.get("reason") or ""),
            order=int(data.get("order") or 0),
            produces_chart=bool(data.get("produces_chart", False)),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class FilterExplanation:
    """A filter applied during analysis."""

    column: str = ""
    operator: str = ""
    value: Any = None
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FilterExplanation":
        data = data or {}
        return cls(
            column=str(data.get("column") or ""),
            operator=str(data.get("operator") or ""),
            value=data.get("value"),
            label=str(data.get("label") or ""),
        )


@dataclass
class ExplanationInput:
    """
    Inputs accepted by the explainer.

    All fields are optional/flexible — callers may pass dicts or domain objects.
    """

    question: str = ""
    analysis_result: Optional[dict[str, Any]] = None
    execution_plan: Optional[dict[str, Any]] = None
    datasets_used: list[dict[str, Any]] = field(default_factory=list)
    join_plan: Optional[dict[str, Any]] = None
    # Optional extras
    filters: list[dict[str, Any]] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    tools_executed: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    confidence: Optional[float] = None
    style: ExplanationStyle = ExplanationStyle.DETAILED
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        *,
        question: str = "",
        analysis_result: Any = None,
        execution_plan: Any = None,
        datasets_used: Any = None,
        join_plan: Any = None,
        filters: Any = None,
        columns_used: Any = None,
        tools_executed: Any = None,
        warnings: Any = None,
        errors: Any = None,
        confidence: Any = None,
        style: Any = ExplanationStyle.DETAILED,
        metadata: Any = None,
        **kwargs: Any,
    ) -> "ExplanationInput":
        style_enum = _as_style(style)
        return cls(
            question=(question or kwargs.get("question") or "").strip(),
            analysis_result=_as_dict(analysis_result),
            execution_plan=_as_dict(execution_plan),
            datasets_used=_as_list_of_dicts(datasets_used),
            join_plan=_as_dict(join_plan),
            filters=_as_list_of_dicts(filters),
            columns_used=[str(c) for c in (columns_used or [])],
            tools_executed=_as_list_of_dicts(tools_executed),
            warnings=[str(w) for w in (warnings or [])],
            errors=[str(e) for e in (errors or [])],
            confidence=_as_float(confidence),
            style=style_enum,
            metadata=dict(metadata or {}),
        )


@dataclass
class ExplanationResult:
    """Structured explanation of how an answer was produced."""

    style: ExplanationStyle = ExplanationStyle.DETAILED
    summary: str = ""
    # Structured sections
    datasets_used: list[DatasetCitation] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    filters_applied: list[FilterExplanation] = field(default_factory=list)
    joins_performed: Optional[JoinExplanation] = None
    tools_executed: list[ToolStepExplanation] = field(default_factory=list)
    reasoning_summary: str = ""
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    citations: list[DatasetCitation] = field(default_factory=list)
    # Rendered narratives for UI
    short_text: str = ""
    detailed_text: str = ""
    technical_text: str = ""
    # The text matching requested style
    explanation_text: str = ""
    explainer: str = "rule_based"
    question: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style.value if isinstance(self.style, ExplanationStyle) else self.style,
            "summary": self.summary,
            "datasets_used": [d.to_dict() for d in self.datasets_used],
            "sources": list(self.sources),
            "columns_used": list(self.columns_used),
            "filters_applied": [f.to_dict() for f in self.filters_applied],
            "joins_performed": self.joins_performed.to_dict() if self.joins_performed else None,
            "tools_executed": [t.to_dict() for t in self.tools_executed],
            "reasoning_summary": self.reasoning_summary,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "citations": [c.to_dict() for c in self.citations],
            "short_text": self.short_text,
            "detailed_text": self.detailed_text,
            "technical_text": self.technical_text,
            "explanation_text": self.explanation_text,
            "explainer": self.explainer,
            "question": self.question,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ExplanationResult":
        data = data or {}
        joins = data.get("joins_performed")
        return cls(
            style=_as_style(data.get("style")),
            summary=str(data.get("summary") or ""),
            datasets_used=[
                DatasetCitation.from_dict(d) for d in (data.get("datasets_used") or [])
            ],
            sources=list(data.get("sources") or []),
            columns_used=list(data.get("columns_used") or []),
            filters_applied=[
                FilterExplanation.from_dict(f) for f in (data.get("filters_applied") or [])
            ],
            joins_performed=JoinExplanation.from_dict(joins) if joins else None,
            tools_executed=[
                ToolStepExplanation.from_dict(t) for t in (data.get("tools_executed") or [])
            ],
            reasoning_summary=str(data.get("reasoning_summary") or ""),
            confidence=float(data.get("confidence") or 0.0),
            warnings=list(data.get("warnings") or []),
            limitations=list(data.get("limitations") or []),
            citations=[DatasetCitation.from_dict(c) for c in (data.get("citations") or [])],
            short_text=str(data.get("short_text") or ""),
            detailed_text=str(data.get("detailed_text") or ""),
            technical_text=str(data.get("technical_text") or ""),
            explanation_text=str(data.get("explanation_text") or ""),
            explainer=str(data.get("explainer") or "rule_based"),
            question=str(data.get("question") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _as_dict(value: Any) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except TypeError:
            # ExecutionResult.to_dict(include_dataframe=...)
            return value.to_dict()
    # Named tuple / simple object
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
        if hasattr(value, "to_dict"):
            return [_as_dict(value) or {}]
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        d = _as_dict(item)
        if d:
            out.append(d)
        elif item is not None:
            out.append({"value": str(item)})
    return out


def _as_style(value: Any) -> ExplanationStyle:
    if isinstance(value, ExplanationStyle):
        return value
    if value is None:
        return ExplanationStyle.DETAILED
    try:
        return ExplanationStyle(str(value).lower())
    except ValueError:
        return ExplanationStyle.DETAILED


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
