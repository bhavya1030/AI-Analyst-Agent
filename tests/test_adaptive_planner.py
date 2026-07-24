"""Tests for Adaptive Planning (Task 22)."""

from __future__ import annotations

import pytest

from backend.adaptive_planning import (
    AdaptiveExecutionPlan,
    AdaptivePlanner,
    PlanStatus,
    PlanStep,
    ReplanTrigger,
    StepObservation,
    StepStatus,
    StepType,
    create_adaptive_plan,
    reset_adaptive_planner,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_adaptive_planner()
    yield
    reset_adaptive_planner()


@pytest.fixture
def planner() -> AdaptivePlanner:
    return AdaptivePlanner()


# ---------------------------------------------------------------------------
# Initial plan
# ---------------------------------------------------------------------------


def test_create_default_plan(planner: AdaptivePlanner):
    plan = planner.create_plan("Forecast India's GDP")
    assert isinstance(plan, AdaptiveExecutionPlan)
    assert plan.plan_id
    assert plan.status == PlanStatus.PENDING
    assert plan.state == PlanStatus.PENDING
    assert plan.completed_steps == []
    assert len(plan.remaining_steps) >= 4
    assert any(s.step_type == StepType.FORECAST for s in plan.remaining_steps)
    assert plan.reason


def test_create_comparison_plan_includes_join(planner: AdaptivePlanner):
    plan = planner.create_plan("Compare India and China GDP")
    types = [s.step_type for s in plan.remaining_steps]
    assert StepType.JOIN in types or StepType.RETRIEVE in types


def test_create_from_explicit_steps(planner: AdaptivePlanner):
    steps = [
        {"step_id": "a", "name": "Retrieve", "step_type": "retrieve"},
        {"step_id": "b", "name": "Analyze", "step_type": "analyze", "depends_on": ["a"]},
    ]
    plan = planner.create_plan("Analyze X", steps)
    assert len(plan.remaining_steps) == 2
    assert plan.remaining_steps[0].step_id == "a"


def test_create_from_tool_plan(planner: AdaptivePlanner):
    plan = planner.create_from_tool_plan(
        "Forecast GDP",
        ["forecast", "trend", "visualization"],
    )
    ids = [s.params.get("tool_id") for s in plan.remaining_steps if s.params.get("tool_id")]
    assert "forecast" in ids
    assert any(s.step_type == StepType.RETRIEVE for s in plan.remaining_steps)


# ---------------------------------------------------------------------------
# Step loop: next + observe success
# ---------------------------------------------------------------------------


def test_happy_path_completes(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "Simple run",
        [
            PlanStep(step_id="s1", name="One", step_type=StepType.ANALYZE),
            PlanStep(step_id="s2", name="Two", step_type=StepType.EXPLAIN, depends_on=["s1"]),
        ],
    )
    planner.start(plan.plan_id)

    step1 = planner.next_step(plan.plan_id)
    assert step1 is not None
    assert step1.step_id == "s1"
    assert step1.status == StepStatus.RUNNING

    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s1", success=True, result={"ok": True}, confidence=0.8),
    )
    assert len(plan.completed_steps) == 1
    assert len(plan.remaining_steps) == 1

    step2 = planner.next_step(plan.plan_id)
    assert step2.step_id == "s2"
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s2", success=True, result={"ok": True}, confidence=0.8),
    )
    assert plan.status == PlanStatus.COMPLETED
    assert plan.state == PlanStatus.COMPLETED
    assert plan.remaining_steps == []
    assert len(plan.completed_steps) == 2


# ---------------------------------------------------------------------------
# Control ops
# ---------------------------------------------------------------------------


def test_pause_resume(planner: AdaptivePlanner):
    plan = planner.create_plan("q", [PlanStep(step_id="s1", name="A"), PlanStep(step_id="s2", name="B")])
    planner.start(plan.plan_id)
    step = planner.next_step(plan.plan_id)
    assert step.step_id == "s1"
    plan = planner.pause(plan.plan_id, reason="user break")
    assert plan.status == PlanStatus.PAUSED
    assert planner.next_step(plan.plan_id) is None  # blocked while paused

    plan = planner.resume(plan.plan_id)
    assert plan.status == PlanStatus.RUNNING
    # Interrupted step is re-dispatched after pause
    step = planner.next_step(plan.plan_id)
    assert step is not None
    assert step.step_id == "s1"
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s1", success=True, result={}, confidence=0.9),
    )
    step = planner.next_step(plan.plan_id)
    assert step is not None
    assert step.step_id == "s2"


def test_cancel(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "q",
        [PlanStep(step_id="s1", name="A"), PlanStep(step_id="s2", name="B")],
    )
    planner.start(plan.plan_id)
    plan = planner.cancel(plan.plan_id, reason="stop")
    assert plan.status == PlanStatus.CANCELLED
    assert planner.next_step(plan.plan_id) is None
    assert all(s.status == StepStatus.SKIPPED for s in plan.remaining_steps)


def test_retry_failed_step(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "q",
        [PlanStep(step_id="s1", name="A", max_attempts=3)],
    )
    planner.start(plan.plan_id)
    planner.next_step(plan.plan_id)
    # Fail without auto replan recovery replacing — force failure observe with auto_replan
    # First failure with attempts remaining → retry
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s1", success=False, error="transient"),
        auto_replan=True,
    )
    # Should have retried s1 back into remaining
    assert plan.status in {PlanStatus.RUNNING, PlanStatus.WAITING_REPLAN}
    # Either retry moved step back or replan recovery
    ids = [s.step_id for s in plan.remaining_steps]
    assert "s1" in ids or any("recover" in s.step_id or "re_" in s.step_id for s in plan.remaining_steps)


def test_manual_replan(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "q",
        [
            PlanStep(step_id="s1", name="Old1"),
            PlanStep(step_id="s2", name="Old2"),
        ],
    )
    planner.start(plan.plan_id)
    plan = planner.replan(
        plan.plan_id,
        [PlanStep(step_id="n1", name="New path", step_type=StepType.RETRIEVE)],
        reason="Manual override",
        trigger=ReplanTrigger.MANUAL,
    )
    assert plan.replan_count == 1
    assert len(plan.remaining_steps) == 1
    assert plan.remaining_steps[0].step_id == "n1"
    assert plan.replanned_steps  # old remaining marked replaced
    assert plan.last_trigger == ReplanTrigger.MANUAL
    assert "Manual" in plan.reason or "override" in plan.reason.lower()


# ---------------------------------------------------------------------------
# Replan triggers
# ---------------------------------------------------------------------------


def test_trigger_dataset_not_found(planner: AdaptivePlanner):
    plan = planner.create_plan("Analyze GDP")
    planner.start(plan.plan_id)
    step = planner.next_step(plan.plan_id)
    assert step.step_type == StepType.RETRIEVE
    plan = planner.observe(
        plan.plan_id,
        StepObservation(
            step_id=step.step_id,
            success=False,
            dataset_found=False,
            error="NOT_FOUND",
            result={"status": "NOT_FOUND"},
        ),
    )
    assert plan.replan_count >= 1 or plan.last_trigger == ReplanTrigger.DATASET_NOT_FOUND
    # New remaining should include alternate search
    names = " ".join(s.name.lower() for s in plan.remaining_steps)
    assert "alternate" in names or "search" in names or plan.replan_count >= 1
    assert plan.last_trigger in {
        ReplanTrigger.DATASET_NOT_FOUND,
        ReplanTrigger.STEP_FAILURE,
    }


def test_trigger_low_confidence(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "Analyze X",
        [
            PlanStep(step_id="s1", name="Analyze", step_type=StepType.ANALYZE),
            PlanStep(step_id="s2", name="Explain", step_type=StepType.EXPLAIN),
        ],
    )
    planner.start(plan.plan_id)
    planner.next_step(plan.plan_id)
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s1", success=True, confidence=0.15, result={"confidence": 0.15}),
    )
    assert plan.last_trigger == ReplanTrigger.LOW_CONFIDENCE or plan.replan_count >= 1
    types = [s.step_type for s in plan.remaining_steps]
    assert StepType.REFLECT in types or StepType.RETRIEVE in types or plan.replan_count >= 1


def test_trigger_unexpected_schema(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "q",
        [PlanStep(step_id="s1", name="Profile", step_type=StepType.PROFILE)],
    )
    planner.start(plan.plan_id)
    planner.next_step(plan.plan_id)
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s1", success=True, schema_ok=False, result={"schema_error": True}),
    )
    assert plan.last_trigger == ReplanTrigger.UNEXPECTED_SCHEMA
    assert plan.replan_count >= 1
    assert any("align" in s.name.lower() or s.step_type == StepType.JOIN for s in plan.remaining_steps)


def test_trigger_poor_join(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "Compare A and B",
        [PlanStep(step_id="s1", name="Join", step_type=StepType.JOIN)],
    )
    planner.start(plan.plan_id)
    planner.next_step(plan.plan_id)
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s1", success=False, join_ok=False, error="incompatible schemas"),
    )
    assert plan.last_trigger in {ReplanTrigger.POOR_JOIN, ReplanTrigger.STEP_FAILURE}
    if plan.replan_count:
        assert any(
            s.step_type == StepType.JOIN or "join" in s.name.lower()
            for s in plan.remaining_steps
        )


def test_trigger_empty_result(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "q",
        [PlanStep(step_id="s1", name="Retrieve", step_type=StepType.RETRIEVE)],
    )
    planner.start(plan.plan_id)
    planner.next_step(plan.plan_id)
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s1", success=True, empty_result=True, result={"rows": 0}),
    )
    assert plan.last_trigger == ReplanTrigger.EMPTY_RESULT
    assert plan.replan_count >= 1


def test_trigger_user_interruption_pauses(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "q",
        [PlanStep(step_id="s1", name="A"), PlanStep(step_id="s2", name="B")],
    )
    planner.start(plan.plan_id)
    planner.next_step(plan.plan_id)
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id="s1", success=False, user_interrupt=True),
    )
    assert plan.status == PlanStatus.PAUSED
    assert plan.last_trigger == ReplanTrigger.USER_INTERRUPTION


def test_trigger_new_follow_up(planner: AdaptivePlanner):
    plan = planner.create_plan(
        "Analyze GDP",
        [PlanStep(step_id="s1", name="Done", step_type=StepType.ANALYZE)],
    )
    planner.start(plan.plan_id)
    planner.next_step(plan.plan_id)
    plan = planner.observe(
        plan.plan_id,
        StepObservation(
            step_id="s1",
            success=True,
            follow_up_question="Now compare it with China",
            confidence=0.8,
        ),
    )
    assert plan.last_trigger == ReplanTrigger.NEW_FOLLOW_UP
    assert plan.replan_count >= 1
    assert plan.remaining_steps
    # Follow-up plan should mention compare/join path ideally
    blob = " ".join(s.name.lower() for s in plan.remaining_steps)
    assert "retrieve" in blob or "analyze" in blob or "join" in blob


# ---------------------------------------------------------------------------
# AdaptiveExecutionPlan fields
# ---------------------------------------------------------------------------


def test_execution_plan_fields_and_to_dict(planner: AdaptivePlanner):
    plan = planner.create_plan("Forecast inflation")
    planner.start(plan.plan_id)
    step = planner.next_step(plan.plan_id)
    plan = planner.observe(
        plan.plan_id,
        StepObservation(step_id=step.step_id, success=True, confidence=0.9, dataset_found=True),
    )
    d = plan.to_dict()
    assert "completed_steps" in d
    assert "remaining_steps" in d
    assert "replanned_steps" in d
    assert "state" in d
    assert "reason" in d
    assert d["state"] == d["status"]
    back = AdaptiveExecutionPlan.from_dict(d)
    assert back.plan_id == plan.plan_id
    assert len(back.completed_steps) == len(plan.completed_steps)


def test_module_level_create():
    plan = create_adaptive_plan("Show population trend")
    assert plan.remaining_steps
    assert plan.status == PlanStatus.PENDING


def test_max_replans(planner: AdaptivePlanner):
    planner.max_replans = 2
    plan = planner.create_plan("q", [PlanStep(step_id="s1", name="A")])
    for i in range(2):
        plan = planner.replan(
            plan.plan_id,
            [PlanStep(step_id=f"n{i}", name=f"N{i}")],
            reason=f"replan {i}",
        )
    assert plan.replan_count == 2
    plan = planner.replan(
        plan.plan_id,
        [PlanStep(step_id="overflow", name="Too many")],
        reason="one more",
    )
    assert plan.status == PlanStatus.FAILED
    assert "Max replans" in plan.reason


def test_snapshot(planner: AdaptivePlanner):
    plan = planner.create_plan("q")
    snap = planner.snapshot(plan.plan_id)
    assert snap.plan_id == plan.plan_id
    assert snap.remaining_steps
