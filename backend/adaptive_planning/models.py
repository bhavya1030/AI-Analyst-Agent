"""Models for Adaptive Planning.

Observe intermediate results and revise remaining execution steps.
Does not redesign the existing Planner; works alongside it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PlanStatus(str, Enum):
    """Lifecycle of an adaptive execution plan."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_REPLAN = "waiting_replan"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"
    REPLACED = "replaced"  # superseded by replan


class StepType(str, Enum):
    """Generic step kinds (map to existing agents later)."""

    RETRIEVE = "retrieve"
    ACQUIRE = "acquire"
    PROFILE = "profile"
    JOIN = "join"
    ANALYZE = "analyze"
    FORECAST = "forecast"
    VISUALIZE = "visualize"
    EXPLAIN = "explain"
    REFLECT = "reflect"
    CUSTOM = "custom"


class ReplanTrigger(str, Enum):
    """Why a replan was requested."""

    DATASET_NOT_FOUND = "dataset_not_found"
    LOW_CONFIDENCE = "low_confidence"
    UNEXPECTED_SCHEMA = "unexpected_schema"
    POOR_JOIN = "poor_join"
    EMPTY_RESULT = "empty_result"
    USER_INTERRUPTION = "user_interruption"
    NEW_FOLLOW_UP = "new_follow_up"
    STEP_FAILURE = "step_failure"
    MANUAL = "manual"
    NONE = "none"


@dataclass
class PlanStep:
    """One step in an adaptive execution plan."""

    step_id: str
    name: str
    step_type: StepType = StepType.CUSTOM
    status: StepStatus = StepStatus.PENDING
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    attempt: int = 0
    max_attempts: int = 2
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "step_type": self.step_type.value
            if isinstance(self.step_type, StepType)
            else self.step_type,
            "status": self.status.value
            if isinstance(self.status, StepStatus)
            else self.status,
            "params": dict(self.params),
            "depends_on": list(self.depends_on),
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PlanStep":
        data = data or {}
        st = data.get("step_type") or StepType.CUSTOM
        if isinstance(st, str):
            try:
                st = StepType(st)
            except ValueError:
                st = StepType.CUSTOM
        ss = data.get("status") or StepStatus.PENDING
        if isinstance(ss, str):
            try:
                ss = StepStatus(ss)
            except ValueError:
                ss = StepStatus.PENDING
        return cls(
            step_id=str(data.get("step_id") or data.get("id") or ""),
            name=str(data.get("name") or ""),
            step_type=st,
            status=ss,
            params=dict(data.get("params") or {}),
            depends_on=[str(d) for d in (data.get("depends_on") or [])],
            attempt=int(data.get("attempt") or 0),
            max_attempts=int(data.get("max_attempts") or 2),
            result=data.get("result") if isinstance(data.get("result"), dict) else None,
            error=data.get("error"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            notes=list(data.get("notes") or []),
        )


@dataclass
class StepObservation:
    """
    Observation recorded after a step executes (or fails).

    Callers feed this back into the adaptive planner — the planner itself
    does not run agents.
    """

    step_id: str
    success: bool
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    # Optional signals that drive replan triggers
    dataset_found: Optional[bool] = None
    confidence: Optional[float] = None
    schema_ok: Optional[bool] = None
    join_ok: Optional[bool] = None
    empty_result: Optional[bool] = None
    user_interrupt: bool = False
    follow_up_question: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StepObservation":
        data = data or {}
        return cls(
            step_id=str(data.get("step_id") or ""),
            success=bool(data.get("success")),
            result=data.get("result") if isinstance(data.get("result"), dict) else None,
            error=data.get("error"),
            dataset_found=data.get("dataset_found"),
            confidence=_as_float(data.get("confidence")),
            schema_ok=data.get("schema_ok"),
            join_ok=data.get("join_ok"),
            empty_result=data.get("empty_result"),
            user_interrupt=bool(data.get("user_interrupt")),
            follow_up_question=data.get("follow_up_question"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ReplanDecision:
    """Outcome of evaluating whether to replan after an observation."""

    need_replan: bool
    trigger: ReplanTrigger = ReplanTrigger.NONE
    reason: str = ""
    suggested_steps: list[PlanStep] = field(default_factory=list)
    skip_remaining: bool = False
    retry_step_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "need_replan": self.need_replan,
            "trigger": self.trigger.value
            if isinstance(self.trigger, ReplanTrigger)
            else self.trigger,
            "reason": self.reason,
            "suggested_steps": [s.to_dict() for s in self.suggested_steps],
            "skip_remaining": self.skip_remaining,
            "retry_step_id": self.retry_step_id,
        }


@dataclass
class AdaptiveExecutionPlan:
    """
    Live adaptive plan state exposed to callers.

    Fields required by Task 22:
      completed_steps, remaining_steps, replanned_steps, state, reason
    """

    plan_id: str
    question: str = ""
    status: PlanStatus = PlanStatus.PENDING
    completed_steps: list[PlanStep] = field(default_factory=list)
    remaining_steps: list[PlanStep] = field(default_factory=list)
    replanned_steps: list[PlanStep] = field(default_factory=list)
    # Alias used in requirements as "state"
    state: PlanStatus = PlanStatus.PENDING
    reason: str = ""
    current_step_id: Optional[str] = None
    replan_count: int = 0
    last_trigger: ReplanTrigger = ReplanTrigger.NONE
    observations: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def sync_state(self) -> None:
        """Keep `state` and `status` aligned."""
        self.state = self.status
        self.updated_at = _utc_now_iso()

    def all_steps(self) -> list[PlanStep]:
        return list(self.completed_steps) + list(self.remaining_steps)

    def to_dict(self) -> dict[str, Any]:
        self.sync_state()
        return {
            "plan_id": self.plan_id,
            "question": self.question,
            "status": self.status.value
            if isinstance(self.status, PlanStatus)
            else self.status,
            "state": self.state.value if isinstance(self.state, PlanStatus) else self.state,
            "reason": self.reason,
            "completed_steps": [s.to_dict() for s in self.completed_steps],
            "remaining_steps": [s.to_dict() for s in self.remaining_steps],
            "replanned_steps": [s.to_dict() for s in self.replanned_steps],
            "current_step_id": self.current_step_id,
            "replan_count": self.replan_count,
            "last_trigger": self.last_trigger.value
            if isinstance(self.last_trigger, ReplanTrigger)
            else self.last_trigger,
            "observations": list(self.observations),
            "history": list(self.history),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AdaptiveExecutionPlan":
        data = data or {}
        status = data.get("status") or data.get("state") or PlanStatus.PENDING
        if isinstance(status, str):
            try:
                status = PlanStatus(status)
            except ValueError:
                status = PlanStatus.PENDING
        trigger = data.get("last_trigger") or ReplanTrigger.NONE
        if isinstance(trigger, str):
            try:
                trigger = ReplanTrigger(trigger)
            except ValueError:
                trigger = ReplanTrigger.NONE
        plan = cls(
            plan_id=str(data.get("plan_id") or ""),
            question=str(data.get("question") or ""),
            status=status,
            completed_steps=[
                PlanStep.from_dict(s) for s in (data.get("completed_steps") or [])
            ],
            remaining_steps=[
                PlanStep.from_dict(s) for s in (data.get("remaining_steps") or [])
            ],
            replanned_steps=[
                PlanStep.from_dict(s) for s in (data.get("replanned_steps") or [])
            ],
            state=status,
            reason=str(data.get("reason") or ""),
            current_step_id=data.get("current_step_id"),
            replan_count=int(data.get("replan_count") or 0),
            last_trigger=trigger,
            observations=list(data.get("observations") or []),
            history=list(data.get("history") or []),
            created_at=data.get("created_at") or _utc_now_iso(),
            updated_at=data.get("updated_at") or _utc_now_iso(),
            metadata=dict(data.get("metadata") or {}),
        )
        return plan


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
