"""Models for Conversation Context Manager.

References only — never store DataFrames or large binary payloads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ReferenceKind(str, Enum):
    """Kinds of anaphoric / contextual references."""

    IT = "it"
    THEM = "them"
    THIS = "this"
    THAT = "that"
    SAME_DATASET = "same_dataset"
    PREVIOUS_CHART = "previous_chart"
    THAT_COUNTRY = "that_country"
    LAST_ANALYSIS = "last_analysis"
    SAME_FILTER = "same_filter"
    PREVIOUS_YEARS = "previous_years"
    ACTIVE_METRIC = "active_metric"
    UNKNOWN = "unknown"


@dataclass
class DatasetRef:
    """Pointer to a dataset — no DataFrame payload."""

    dataset_id: Optional[str] = None
    local_path: Optional[str] = None
    download_url: Optional[str] = None
    topic: str = ""
    source: Optional[str] = None
    columns: list[str] = field(default_factory=list)
    row_count: Optional[int] = None
    registry_id: Optional[str] = None
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DatasetRef":
        data = data or {}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        payload.setdefault("topic", "")
        payload.setdefault("columns", [])
        payload.setdefault("is_active", True)
        payload.setdefault("metadata", {})
        return cls(**payload)


@dataclass
class FilterSpec:
    """Declarative filter applied during analysis (reference only)."""

    column: str
    operator: str  # eq, ne, gt, gte, lt, lte, in, between, contains
    value: Any = None
    value_to: Any = None  # for between
    label: str = ""  # human-readable e.g. "Year > 2010"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FilterSpec":
        data = data or {}
        return cls(
            column=str(data.get("column") or ""),
            operator=str(data.get("operator") or "eq"),
            value=data.get("value"),
            value_to=data.get("value_to"),
            label=str(data.get("label") or ""),
        )


@dataclass
class VisualizationRef:
    """Reference to a previous chart — not the chart payload itself."""

    chart_type: Optional[str] = None
    columns: list[str] = field(default_factory=list)
    title: Optional[str] = None
    chart_id: Optional[str] = None
    # Optional small fingerprint (e.g. hash or path), never full Plotly JSON by default
    artifact_ref: Optional[str] = None
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "VisualizationRef":
        data = data or {}
        return cls(
            chart_type=data.get("chart_type"),
            columns=list(data.get("columns") or []),
            title=data.get("title"),
            chart_id=data.get("chart_id"),
            artifact_ref=data.get("artifact_ref"),
            created_at=data.get("created_at") or _utc_now_iso(),
        )


@dataclass
class AnalysisStep:
    """One step in the conversation analysis history."""

    operation: str = ""  # analyze, forecast, visualize, compare, filter, eda, ...
    intent: Optional[str] = None
    question: str = ""
    resolved_question: str = ""
    summary: str = ""
    metrics: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    dataset_topics: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AnalysisStep":
        data = data or {}
        return cls(
            operation=str(data.get("operation") or ""),
            intent=data.get("intent"),
            question=str(data.get("question") or ""),
            resolved_question=str(data.get("resolved_question") or ""),
            summary=str(data.get("summary") or ""),
            metrics=list(data.get("metrics") or []),
            countries=list(data.get("countries") or []),
            dataset_topics=list(data.get("dataset_topics") or []),
            timestamp=data.get("timestamp") or _utc_now_iso(),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ConversationContext:
    """
    Full conversational memory for one conversation_id.

    Never stores DataFrames — only DatasetRef and other lightweight refs.
    """

    conversation_id: str
    active_datasets: list[DatasetRef] = field(default_factory=list)
    filters: list[FilterSpec] = field(default_factory=list)
    selected_countries: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    visualizations: list[VisualizationRef] = field(default_factory=list)
    analysis_steps: list[AnalysisStep] = field(default_factory=list)
    last_question: str = ""
    last_resolved_question: str = ""
    last_intent: Optional[str] = None
    last_operation: Optional[str] = None
    last_forecast_target: Optional[str] = None
    last_columns: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)  # free-form entities mentioned
    notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    last_activity_at: str = field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def active_dataset(self) -> Optional[DatasetRef]:
        for d in self.active_datasets:
            if d.is_active:
                return d
        return self.active_datasets[-1] if self.active_datasets else None

    def last_chart(self) -> Optional[VisualizationRef]:
        return self.visualizations[-1] if self.visualizations else None

    def last_analysis(self) -> Optional[AnalysisStep]:
        return self.analysis_steps[-1] if self.analysis_steps else None

    def primary_topic(self) -> str:
        ds = self.active_dataset()
        if ds and ds.topic:
            return ds.topic
        if self.last_forecast_target:
            return self.last_forecast_target
        if self.metrics:
            return self.metrics[0]
        return ""

    def touch(self) -> None:
        now = _utc_now_iso()
        self.updated_at = now
        self.last_activity_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "active_datasets": [d.to_dict() for d in self.active_datasets],
            "filters": [f.to_dict() for f in self.filters],
            "selected_countries": list(self.selected_countries),
            "metrics": list(self.metrics),
            "visualizations": [v.to_dict() for v in self.visualizations],
            "analysis_steps": [a.to_dict() for a in self.analysis_steps],
            "last_question": self.last_question,
            "last_resolved_question": self.last_resolved_question,
            "last_intent": self.last_intent,
            "last_operation": self.last_operation,
            "last_forecast_target": self.last_forecast_target,
            "last_columns": list(self.last_columns),
            "entities": list(self.entities),
            "notes": list(self.notes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_activity_at": self.last_activity_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConversationContext":
        if not data:
            raise ValueError("context dict is required")
        cid = (data.get("conversation_id") or "").strip()
        if not cid:
            raise ValueError("conversation_id is required")
        return cls(
            conversation_id=cid,
            active_datasets=[
                DatasetRef.from_dict(d) for d in (data.get("active_datasets") or [])
            ],
            filters=[FilterSpec.from_dict(f) for f in (data.get("filters") or [])],
            selected_countries=list(data.get("selected_countries") or []),
            metrics=list(data.get("metrics") or []),
            visualizations=[
                VisualizationRef.from_dict(v) for v in (data.get("visualizations") or [])
            ],
            analysis_steps=[
                AnalysisStep.from_dict(a) for a in (data.get("analysis_steps") or [])
            ],
            last_question=str(data.get("last_question") or ""),
            last_resolved_question=str(data.get("last_resolved_question") or ""),
            last_intent=data.get("last_intent"),
            last_operation=data.get("last_operation"),
            last_forecast_target=data.get("last_forecast_target"),
            last_columns=list(data.get("last_columns") or []),
            entities=list(data.get("entities") or []),
            notes=list(data.get("notes") or []),
            created_at=data.get("created_at") or _utc_now_iso(),
            updated_at=data.get("updated_at") or _utc_now_iso(),
            last_activity_at=data.get("last_activity_at") or _utc_now_iso(),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ResolvedReference:
    """One resolved anaphor / phrase within a question."""

    kind: ReferenceKind
    original_span: str
    resolved_value: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value if isinstance(self.kind, ReferenceKind) else self.kind,
            "original_span": self.original_span,
            "resolved_value": self.resolved_value,
            "detail": dict(self.detail),
        }


@dataclass
class ResolvedRequest:
    """
    Planner-ready request produced from raw user text + conversation context.

    Planner is not modified yet; this is the future input contract.
    """

    conversation_id: str
    original_question: str
    resolved_question: str
    is_follow_up: bool = False
    reuse_active_dataset: bool = False
    dataset_refs: list[DatasetRef] = field(default_factory=list)
    filters: list[FilterSpec] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    last_chart: Optional[VisualizationRef] = None
    last_analysis: Optional[AnalysisStep] = None
    resolved_references: list[ResolvedReference] = field(default_factory=list)
    primary_topic: str = ""
    last_operation: Optional[str] = None
    last_intent: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "original_question": self.original_question,
            "resolved_question": self.resolved_question,
            "is_follow_up": self.is_follow_up,
            "reuse_active_dataset": self.reuse_active_dataset,
            "dataset_refs": [d.to_dict() for d in self.dataset_refs],
            "filters": [f.to_dict() for f in self.filters],
            "countries": list(self.countries),
            "metrics": list(self.metrics),
            "last_chart": self.last_chart.to_dict() if self.last_chart else None,
            "last_analysis": self.last_analysis.to_dict() if self.last_analysis else None,
            "resolved_references": [r.to_dict() for r in self.resolved_references],
            "primary_topic": self.primary_topic,
            "last_operation": self.last_operation,
            "last_intent": self.last_intent,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ResolvedRequest":
        data = data or {}
        last_chart = data.get("last_chart")
        last_analysis = data.get("last_analysis")
        return cls(
            conversation_id=str(data.get("conversation_id") or ""),
            original_question=str(data.get("original_question") or ""),
            resolved_question=str(data.get("resolved_question") or ""),
            is_follow_up=bool(data.get("is_follow_up")),
            reuse_active_dataset=bool(data.get("reuse_active_dataset")),
            dataset_refs=[
                DatasetRef.from_dict(d) for d in (data.get("dataset_refs") or [])
            ],
            filters=[FilterSpec.from_dict(f) for f in (data.get("filters") or [])],
            countries=list(data.get("countries") or []),
            metrics=list(data.get("metrics") or []),
            last_chart=VisualizationRef.from_dict(last_chart) if last_chart else None,
            last_analysis=AnalysisStep.from_dict(last_analysis) if last_analysis else None,
            resolved_references=[
                ResolvedReference(
                    kind=ReferenceKind(r.get("kind"))
                    if r.get("kind") in ReferenceKind._value2member_map_
                    else ReferenceKind.UNKNOWN,
                    original_span=str(r.get("original_span") or ""),
                    resolved_value=str(r.get("resolved_value") or ""),
                    detail=dict(r.get("detail") or {}),
                )
                for r in (data.get("resolved_references") or [])
            ],
            primary_topic=str(data.get("primary_topic") or ""),
            last_operation=data.get("last_operation"),
            last_intent=data.get("last_intent"),
            warnings=list(data.get("warnings") or []),
            metadata=dict(data.get("metadata") or {}),
        )
