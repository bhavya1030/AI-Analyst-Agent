"""Adaptive Planner — revise execution plans from intermediate observations.

Does NOT redesign the existing Planner. Does NOT execute agents.
Callers execute steps and feed StepObservation back.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional, Sequence

from backend.adaptive_planning.models import (
    AdaptiveExecutionPlan,
    PlanStatus,
    PlanStep,
    ReplanDecision,
    ReplanTrigger,
    StepObservation,
    StepStatus,
    StepType,
    _utc_now_iso,
)
from backend.adaptive_planning.prompts import build_replan_prompt
from backend.adaptive_planning.state import AdaptivePlanStore, get_default_store
from backend.core.logger import get_logger

logger = get_logger(__name__)

# Default confidence floor for "low confidence" replan trigger
DEFAULT_LOW_CONFIDENCE = 0.4


class AdaptivePlanner:
    """
    Adaptive planning control loop:

      initial_plan → next_step → observe → (replan|retry|continue) → ...

    Control ops: pause, resume, cancel, retry, replan.
    """

    def __init__(
        self,
        store: AdaptivePlanStore | None = None,
        *,
        low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE,
        max_replans: int = 5,
    ):
        self._store = store or get_default_store()
        self.low_confidence_threshold = low_confidence_threshold
        self.max_replans = max_replans

    # ------------------------------------------------------------------
    # Create / load
    # ------------------------------------------------------------------

    def create_plan(
        self,
        question: str,
        steps: Sequence[PlanStep | dict[str, Any]] | None = None,
        *,
        plan_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdaptiveExecutionPlan:
        """
        Create an initial adaptive plan.

        If steps is None, builds a default analytics pipeline skeleton
        from the question (does not call existing Planner agents).
        """
        pid = (plan_id or f"aplan-{uuid.uuid4().hex[:12]}").strip()
        parsed = self._parse_steps(steps) if steps is not None else self.build_initial_steps(question)
        plan = AdaptiveExecutionPlan(
            plan_id=pid,
            question=(question or "").strip(),
            status=PlanStatus.PENDING,
            state=PlanStatus.PENDING,
            remaining_steps=parsed,
            completed_steps=[],
            replanned_steps=[],
            reason="Initial plan created.",
            metadata=dict(metadata or {}),
        )
        plan.history.append(
            {
                "event": "created",
                "at": _utc_now_iso(),
                "n_steps": len(parsed),
            }
        )
        plan.sync_state()
        return self._store.put(plan)

    def create_from_tool_plan(
        self,
        question: str,
        tool_ids: Sequence[str],
        *,
        include_retrieve: bool = True,
        plan_id: str | None = None,
    ) -> AdaptiveExecutionPlan:
        """
        Convenience: turn tool selection ids into adaptive steps.

        Does not import/modify tool_selection — caller passes tool_ids.
        """
        steps: list[PlanStep] = []
        n = 0
        if include_retrieve:
            n += 1
            steps.append(
                PlanStep(
                    step_id=f"s{n}",
                    name="Retrieve dataset",
                    step_type=StepType.RETRIEVE,
                    params={"topic": question},
                )
            )
            n += 1
            steps.append(
                PlanStep(
                    step_id=f"s{n}",
                    name="Acquire dataset",
                    step_type=StepType.ACQUIRE,
                    depends_on=[steps[-1].step_id],
                )
            )
        for tid in tool_ids:
            n += 1
            stype = _tool_to_step_type(str(tid))
            steps.append(
                PlanStep(
                    step_id=f"s{n}",
                    name=f"Run {tid}",
                    step_type=stype,
                    params={"tool_id": str(tid)},
                    depends_on=[steps[-1].step_id] if steps else [],
                )
            )
        n += 1
        steps.append(
            PlanStep(
                step_id=f"s{n}",
                name="Generate explanation",
                step_type=StepType.EXPLAIN,
                depends_on=[steps[-1].step_id] if steps else [],
            )
        )
        return self.create_plan(question, steps, plan_id=plan_id)

    def get_plan(self, plan_id: str) -> Optional[AdaptiveExecutionPlan]:
        return self._store.get(plan_id)

    # ------------------------------------------------------------------
    # Control: pause / resume / cancel / retry / replan
    # ------------------------------------------------------------------

    def pause(self, plan_id: str, reason: str = "Paused by user") -> AdaptiveExecutionPlan:
        plan = self._require(plan_id)
        if plan.status in {
            PlanStatus.COMPLETED,
            PlanStatus.CANCELLED,
            PlanStatus.FAILED,
        }:
            plan.reason = f"Cannot pause from status={plan.status.value}"
            return self._store.put(plan)
        # Park in-flight step so resume can re-dispatch it
        for s in plan.remaining_steps:
            if s.status == StepStatus.RUNNING:
                s.status = StepStatus.PENDING
                s.notes.append("Paused while running; will resume")
                # Do not count the interrupted attempt against max_attempts
                if s.attempt > 0:
                    s.attempt -= 1
        plan.status = PlanStatus.PAUSED
        plan.reason = reason
        plan.history.append({"event": "pause", "at": _utc_now_iso(), "reason": reason})
        plan.sync_state()
        logger.info("Adaptive plan paused", extra={"plan_id": plan_id})
        return self._store.put(plan)

    def resume(self, plan_id: str, reason: str = "Resumed") -> AdaptiveExecutionPlan:
        plan = self._require(plan_id)
        if plan.status not in {PlanStatus.PAUSED, PlanStatus.WAITING_REPLAN, PlanStatus.PENDING}:
            if plan.status == PlanStatus.RUNNING:
                plan.reason = "Already running"
                return self._store.put(plan)
            plan.reason = f"Cannot resume from status={plan.status.value}"
            return self._store.put(plan)
        if not plan.remaining_steps:
            plan.status = PlanStatus.COMPLETED
            plan.reason = "No remaining steps; marked completed on resume"
        else:
            plan.status = PlanStatus.RUNNING
            plan.reason = reason
        plan.history.append({"event": "resume", "at": _utc_now_iso(), "reason": reason})
        plan.sync_state()
        return self._store.put(plan)

    def cancel(self, plan_id: str, reason: str = "Cancelled by user") -> AdaptiveExecutionPlan:
        plan = self._require(plan_id)
        # Skip pending remaining
        for s in plan.remaining_steps:
            if s.status in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.RETRYING}:
                s.status = StepStatus.SKIPPED
                s.notes.append("Cancelled")
        plan.status = PlanStatus.CANCELLED
        plan.reason = reason
        plan.current_step_id = None
        plan.history.append({"event": "cancel", "at": _utc_now_iso(), "reason": reason})
        plan.sync_state()
        logger.info("Adaptive plan cancelled", extra={"plan_id": plan_id})
        return self._store.put(plan)

    def retry(
        self,
        plan_id: str,
        step_id: str | None = None,
        *,
        reason: str = "Retry requested",
    ) -> AdaptiveExecutionPlan:
        """
        Retry a failed step (or the last completed failed attempt).

        Moves the step back to remaining as PENDING with incremented attempt.
        """
        plan = self._require(plan_id)
        if plan.status == PlanStatus.CANCELLED:
            plan.reason = "Cannot retry a cancelled plan"
            return self._store.put(plan)

        target_id = step_id or plan.current_step_id
        step: PlanStep | None = None
        # Search completed (failed) then remaining
        for s in list(plan.completed_steps) + list(plan.remaining_steps):
            if target_id and s.step_id == target_id:
                step = s
                break
        if step is None and plan.completed_steps:
            # last failed in completed
            for s in reversed(plan.completed_steps):
                if s.status == StepStatus.FAILED:
                    step = s
                    break
        if step is None:
            plan.reason = "No step available to retry"
            return self._store.put(plan)

        if step.attempt >= step.max_attempts:
            plan.reason = f"Step {step.step_id} exhausted max_attempts={step.max_attempts}"
            plan.status = PlanStatus.FAILED
            plan.sync_state()
            return self._store.put(plan)

        # Remove from completed if present
        plan.completed_steps = [s for s in plan.completed_steps if s.step_id != step.step_id]
        # Ensure at front of remaining
        plan.remaining_steps = [s for s in plan.remaining_steps if s.step_id != step.step_id]
        step.status = StepStatus.RETRYING
        step.error = None
        step.result = None
        step.notes.append(reason)
        plan.remaining_steps.insert(0, step)
        plan.status = PlanStatus.RUNNING
        plan.reason = reason
        plan.current_step_id = step.step_id
        plan.history.append(
            {
                "event": "retry",
                "at": _utc_now_iso(),
                "step_id": step.step_id,
                "attempt": step.attempt,
                "reason": reason,
            }
        )
        plan.sync_state()
        return self._store.put(plan)

    def replan(
        self,
        plan_id: str,
        new_steps: Sequence[PlanStep | dict[str, Any]],
        *,
        reason: str = "Manual replan",
        trigger: ReplanTrigger = ReplanTrigger.MANUAL,
        replace_remaining: bool = True,
    ) -> AdaptiveExecutionPlan:
        """Explicitly replace or extend remaining steps."""
        plan = self._require(plan_id)
        if plan.status == PlanStatus.CANCELLED:
            plan.reason = "Cannot replan a cancelled plan"
            return self._store.put(plan)
        if plan.replan_count >= self.max_replans:
            plan.status = PlanStatus.FAILED
            plan.reason = f"Max replans ({self.max_replans}) exceeded"
            plan.sync_state()
            return self._store.put(plan)

        parsed = self._parse_steps(new_steps)
        if replace_remaining:
            # Mark old remaining as replaced
            for s in plan.remaining_steps:
                s.status = StepStatus.REPLACED
                s.notes.append(f"Replaced by replan: {reason}")
                plan.replanned_steps.append(s)
            plan.remaining_steps = parsed
        else:
            plan.remaining_steps.extend(parsed)
            plan.replanned_steps.extend(parsed)

        plan.replan_count += 1
        plan.last_trigger = trigger
        plan.status = PlanStatus.RUNNING if plan.remaining_steps else PlanStatus.COMPLETED
        plan.reason = reason
        plan.history.append(
            {
                "event": "replan",
                "at": _utc_now_iso(),
                "trigger": trigger.value if isinstance(trigger, ReplanTrigger) else trigger,
                "reason": reason,
                "n_new_steps": len(parsed),
                "replace_remaining": replace_remaining,
            }
        )
        plan.sync_state()
        logger.info(
            "Adaptive replan applied",
            extra={"plan_id": plan_id, "trigger": str(trigger), "n": len(parsed)},
        )
        return self._store.put(plan)

    # ------------------------------------------------------------------
    # Execution loop helpers
    # ------------------------------------------------------------------

    def start(self, plan_id: str) -> AdaptiveExecutionPlan:
        plan = self._require(plan_id)
        if plan.status == PlanStatus.CANCELLED:
            return plan
        if not plan.remaining_steps:
            plan.status = PlanStatus.COMPLETED
            plan.reason = "No steps to run"
        else:
            plan.status = PlanStatus.RUNNING
            plan.reason = "Execution started"
        plan.history.append({"event": "start", "at": _utc_now_iso()})
        plan.sync_state()
        return self._store.put(plan)

    def next_step(self, plan_id: str) -> Optional[PlanStep]:
        """
        Peek/start the next pending remaining step.

        Returns None if paused/cancelled/completed or no steps left.
        """
        plan = self._require(plan_id)
        if plan.status in {
            PlanStatus.PAUSED,
            PlanStatus.CANCELLED,
            PlanStatus.COMPLETED,
            PlanStatus.FAILED,
        }:
            return None
        if plan.status == PlanStatus.PENDING:
            plan = self.start(plan_id)

        plan = self._require(plan_id)
        for step in plan.remaining_steps:
            if step.status in {
                StepStatus.PENDING,
                StepStatus.RETRYING,
            }:
                step.status = StepStatus.RUNNING
                step.attempt += 1
                step.started_at = _utc_now_iso()
                plan.current_step_id = step.step_id
                plan.status = PlanStatus.RUNNING
                plan.reason = f"Running step {step.step_id}: {step.name}"
                plan.sync_state()
                self._store.put(plan)
                return step
        # Nothing left
        if not plan.remaining_steps:
            plan.status = PlanStatus.COMPLETED
            plan.reason = "All steps completed"
            plan.current_step_id = None
            plan.sync_state()
            self._store.put(plan)
        return None

    def observe(
        self,
        plan_id: str,
        observation: StepObservation | dict[str, Any],
        *,
        auto_replan: bool = True,
    ) -> AdaptiveExecutionPlan:
        """
        Record step results, mark step complete/failed, evaluate replan.

        If auto_replan and decision.need_replan, applies replan automatically.
        """
        plan = self._require(plan_id)
        if plan.status == PlanStatus.CANCELLED:
            plan.reason = "Ignoring observation on cancelled plan"
            return self._store.put(plan)

        obs = (
            observation
            if isinstance(observation, StepObservation)
            else StepObservation.from_dict(observation)
        )
        plan.observations.append(obs.to_dict())

        # User interrupt → pause
        if obs.user_interrupt:
            plan = self.pause(plan_id, reason="User interruption observed")
            plan.last_trigger = ReplanTrigger.USER_INTERRUPTION
            plan.history.append(
                {"event": "user_interrupt", "at": _utc_now_iso(), "step_id": obs.step_id}
            )
            return self._store.put(plan)

        # Locate step in remaining
        step = None
        for s in plan.remaining_steps:
            if s.step_id == obs.step_id:
                step = s
                break
        if step is None:
            # Allow observe on current_step_id mismatch with warning
            plan.reason = f"Observation for unknown step_id={obs.step_id}"
            plan.history.append(
                {
                    "event": "observe_unknown_step",
                    "at": _utc_now_iso(),
                    "step_id": obs.step_id,
                }
            )
            return self._store.put(plan)

        step.finished_at = _utc_now_iso()
        step.result = obs.result
        if obs.success:
            step.status = StepStatus.COMPLETED
            step.error = None
            plan.remaining_steps = [s for s in plan.remaining_steps if s.step_id != step.step_id]
            plan.completed_steps.append(step)
        else:
            step.status = StepStatus.FAILED
            step.error = obs.error or "Step failed"
            plan.remaining_steps = [s for s in plan.remaining_steps if s.step_id != step.step_id]
            plan.completed_steps.append(step)

        plan.history.append(
            {
                "event": "observe",
                "at": _utc_now_iso(),
                "step_id": obs.step_id,
                "success": obs.success,
                "error": obs.error,
            }
        )

        # Evaluate replan
        decision = self.evaluate_replan(plan, obs)
        if decision.need_replan:
            plan.last_trigger = decision.trigger
            plan.reason = decision.reason
            if decision.retry_step_id and not decision.suggested_steps:
                # Prefer retry
                return self.retry(plan_id, decision.retry_step_id, reason=decision.reason)
            if auto_replan:
                if decision.suggested_steps:
                    return self.replan(
                        plan_id,
                        decision.suggested_steps,
                        reason=decision.reason,
                        trigger=decision.trigger,
                        replace_remaining=True,
                    )
                plan.status = PlanStatus.WAITING_REPLAN
                plan.reason = decision.reason
                plan.sync_state()
                return self._store.put(plan)

        # Continue or complete
        if not plan.remaining_steps:
            if any(s.status == StepStatus.FAILED for s in plan.completed_steps) and not plan.completed_steps:
                plan.status = PlanStatus.FAILED
            elif any(
                s.status == StepStatus.FAILED for s in plan.completed_steps
            ) and not any(s.status == StepStatus.COMPLETED for s in plan.completed_steps):
                plan.status = PlanStatus.FAILED
                plan.reason = "All steps failed"
            else:
                # Partial success still completes if something done or no failures blocking
                failed = [s for s in plan.completed_steps if s.status == StepStatus.FAILED]
                if failed and not plan.completed_steps:
                    plan.status = PlanStatus.FAILED
                else:
                    plan.status = PlanStatus.COMPLETED
                    plan.reason = plan.reason or "Plan completed"
            plan.current_step_id = None
        else:
            plan.status = PlanStatus.RUNNING
            plan.reason = "Continuing with remaining steps"
            plan.current_step_id = None

        plan.sync_state()
        return self._store.put(plan)

    def evaluate_replan(
        self,
        plan: AdaptiveExecutionPlan,
        observation: StepObservation,
    ) -> ReplanDecision:
        """
        Decide whether intermediate results require a replan.

        Triggers:
          dataset_not_found, low_confidence, unexpected_schema, poor_join,
          empty_result, user_interruption, new_follow_up, step_failure
        """
        # User interruption handled in observe via pause
        if observation.user_interrupt:
            return ReplanDecision(
                need_replan=False,
                trigger=ReplanTrigger.USER_INTERRUPTION,
                reason="User interruption — plan paused rather than replanned.",
            )

        # New follow-up question
        if observation.follow_up_question:
            follow = observation.follow_up_question.strip()
            new_steps = self.build_initial_steps(follow)
            # re-id to avoid collisions
            new_steps = self._re_id_steps(new_steps, prefix=f"r{plan.replan_count + 1}")
            return ReplanDecision(
                need_replan=True,
                trigger=ReplanTrigger.NEW_FOLLOW_UP,
                reason=f"New follow-up received: {follow[:120]}",
                suggested_steps=new_steps,
            )

        # Dataset not found
        if observation.dataset_found is False or _flag_in_result(
            observation, "dataset_not_found", "not_found", "NOT_FOUND", "SEARCH_REQUIRED"
        ):
            alt = [
                PlanStep(
                    step_id="re_search",
                    name="Search alternate dataset sources",
                    step_type=StepType.RETRIEVE,
                    params={
                        "topic": plan.question,
                        "force_search": True,
                        "reason": "primary dataset not found",
                    },
                ),
                PlanStep(
                    step_id="re_acquire",
                    name="Acquire alternate dataset",
                    step_type=StepType.ACQUIRE,
                    depends_on=["re_search"],
                ),
                PlanStep(
                    step_id="re_profile",
                    name="Profile alternate dataset",
                    step_type=StepType.PROFILE,
                    depends_on=["re_acquire"],
                ),
            ]
            # Keep non-retrieve remaining analysis steps if any
            tail = [
                s
                for s in plan.remaining_steps
                if s.step_id != observation.step_id
                and s.step_type
                not in {StepType.RETRIEVE, StepType.ACQUIRE}
            ]
            for t in tail:
                t.depends_on = [alt[-1].step_id]
            return ReplanDecision(
                need_replan=True,
                trigger=ReplanTrigger.DATASET_NOT_FOUND,
                reason="Dataset not found — switching to alternate retrieval path.",
                suggested_steps=alt + tail,
            )

        # Empty result
        if observation.empty_result is True or _flag_in_result(
            observation, "empty", "empty_result", "no_rows"
        ):
            return ReplanDecision(
                need_replan=True,
                trigger=ReplanTrigger.EMPTY_RESULT,
                reason="Empty result observed — retry retrieval with broader query or alternate source.",
                suggested_steps=[
                    PlanStep(
                        step_id="re_broaden",
                        name="Broaden dataset search",
                        step_type=StepType.RETRIEVE,
                        params={"topic": plan.question, "broaden": True},
                    ),
                    PlanStep(
                        step_id="re_analyze",
                        name="Re-run analysis on new data",
                        step_type=StepType.ANALYZE,
                        depends_on=["re_broaden"],
                    ),
                ],
            )

        # Unexpected schema
        if observation.schema_ok is False or _flag_in_result(
            observation, "schema_error", "unexpected_schema", "schema_mismatch"
        ):
            return ReplanDecision(
                need_replan=True,
                trigger=ReplanTrigger.UNEXPECTED_SCHEMA,
                reason="Unexpected schema — insert alignment / profile steps before analysis.",
                suggested_steps=[
                    PlanStep(
                        step_id="re_profile",
                        name="Re-profile dataset schema",
                        step_type=StepType.PROFILE,
                        params={"force": True},
                    ),
                    PlanStep(
                        step_id="re_align",
                        name="Align schema / normalize columns",
                        step_type=StepType.JOIN,
                        params={"mode": "align_only"},
                        depends_on=["re_profile"],
                    ),
                    PlanStep(
                        step_id="re_analyze",
                        name="Continue analysis after alignment",
                        step_type=StepType.ANALYZE,
                        depends_on=["re_align"],
                    ),
                ],
            )

        # Poor join
        if observation.join_ok is False or _flag_in_result(
            observation, "poor_join", "join_failed", "incompatible"
        ):
            return ReplanDecision(
                need_replan=True,
                trigger=ReplanTrigger.POOR_JOIN,
                reason="Poor join quality — retry with outer join / concat fallback.",
                suggested_steps=[
                    PlanStep(
                        step_id="re_join",
                        name="Retry join with outer strategy",
                        step_type=StepType.JOIN,
                        params={"strategy": "outer", "fallback": "concat"},
                    ),
                    PlanStep(
                        step_id="re_validate_join",
                        name="Validate join result",
                        step_type=StepType.PROFILE,
                        depends_on=["re_join"],
                    ),
                    PlanStep(
                        step_id="re_analyze",
                        name="Analyze joined data",
                        step_type=StepType.ANALYZE,
                        depends_on=["re_validate_join"],
                    ),
                ],
            )

        # Low confidence
        conf = observation.confidence
        if conf is None and observation.result:
            conf = observation.result.get("confidence")
            try:
                conf = float(conf) if conf is not None else None
            except (TypeError, ValueError):
                conf = None
        if conf is not None and conf < self.low_confidence_threshold:
            return ReplanDecision(
                need_replan=True,
                trigger=ReplanTrigger.LOW_CONFIDENCE,
                reason=(
                    f"Low confidence ({conf:.2f} < {self.low_confidence_threshold}) — "
                    "gather more evidence and reflect."
                ),
                suggested_steps=[
                    PlanStep(
                        step_id="re_retrieve_more",
                        name="Retrieve supporting dataset",
                        step_type=StepType.RETRIEVE,
                        params={"supporting": True, "topic": plan.question},
                    ),
                    PlanStep(
                        step_id="re_analyze",
                        name="Re-analyze with additional data",
                        step_type=StepType.ANALYZE,
                        depends_on=["re_retrieve_more"],
                    ),
                    PlanStep(
                        step_id="re_reflect",
                        name="Reflection quality check",
                        step_type=StepType.REFLECT,
                        depends_on=["re_analyze"],
                    ),
                    PlanStep(
                        step_id="re_explain",
                        name="Update explanation with limitations",
                        step_type=StepType.EXPLAIN,
                        depends_on=["re_reflect"],
                    ),
                ],
            )

        # Hard step failure → retry if attempts remain, else replan
        if not observation.success:
            # Find attempts on completed step (already moved) — use observation step
            failed_attempts = 1
            for s in plan.completed_steps:
                if s.step_id == observation.step_id:
                    failed_attempts = s.attempt
                    max_attempts = s.max_attempts
                    if failed_attempts < max_attempts:
                        return ReplanDecision(
                            need_replan=True,
                            trigger=ReplanTrigger.STEP_FAILURE,
                            reason=f"Step {observation.step_id} failed: {observation.error or 'error'}",
                            retry_step_id=observation.step_id,
                        )
                    break
            # Exhausted or unknown — replan around failure
            recovery = [
                PlanStep(
                    step_id="re_recover",
                    name=f"Recover from failed step {observation.step_id}",
                    step_type=StepType.RETRIEVE,
                    params={"recovery": True, "failed_step": observation.step_id},
                ),
                PlanStep(
                    step_id="re_continue",
                    name="Continue analysis after recovery",
                    step_type=StepType.ANALYZE,
                    depends_on=["re_recover"],
                ),
            ]
            return ReplanDecision(
                need_replan=True,
                trigger=ReplanTrigger.STEP_FAILURE,
                reason=f"Step failure without remaining retries: {observation.error or 'error'}",
                suggested_steps=recovery,
            )

        return ReplanDecision(need_replan=False, trigger=ReplanTrigger.NONE, reason="OK")

    def snapshot(self, plan_id: str) -> AdaptiveExecutionPlan:
        """Return current AdaptiveExecutionPlan (completed / remaining / replanned / state / reason)."""
        return self._require(plan_id)

    # ------------------------------------------------------------------
    # Initial plan construction (standalone — not the existing Planner)
    # ------------------------------------------------------------------

    def build_initial_steps(self, question: str) -> list[PlanStep]:
        """Default step skeleton from a natural-language question."""
        q = (question or "").lower()
        steps: list[PlanStep] = [
            PlanStep(
                step_id="s1",
                name="Retrieve dataset",
                step_type=StepType.RETRIEVE,
                params={"topic": question},
            ),
            PlanStep(
                step_id="s2",
                name="Acquire dataset",
                step_type=StepType.ACQUIRE,
                depends_on=["s1"],
            ),
            PlanStep(
                step_id="s3",
                name="Profile dataset",
                step_type=StepType.PROFILE,
                depends_on=["s2"],
            ),
        ]
        if any(w in q for w in ("compare", "versus", " vs ", "relationship", "correlation")):
            steps.append(
                PlanStep(
                    step_id="s4",
                    name="Retrieve related datasets",
                    step_type=StepType.RETRIEVE,
                    params={"multi": True, "topic": question},
                    depends_on=["s3"],
                )
            )
            steps.append(
                PlanStep(
                    step_id="s5",
                    name="Join / align datasets",
                    step_type=StepType.JOIN,
                    depends_on=["s4"],
                )
            )
            prev = "s5"
        else:
            prev = "s3"

        if any(w in q for w in ("forecast", "predict", "projection")):
            steps.append(
                PlanStep(
                    step_id="s6",
                    name="Forecast",
                    step_type=StepType.FORECAST,
                    depends_on=[prev],
                )
            )
            prev = "s6"
        else:
            steps.append(
                PlanStep(
                    step_id="s6",
                    name="Analyze",
                    step_type=StepType.ANALYZE,
                    depends_on=[prev],
                )
            )
            prev = "s6"

        steps.append(
            PlanStep(
                step_id="s7",
                name="Visualize",
                step_type=StepType.VISUALIZE,
                depends_on=[prev],
            )
        )
        steps.append(
            PlanStep(
                step_id="s8",
                name="Explain",
                step_type=StepType.EXPLAIN,
                depends_on=["s7"],
            )
        )
        return steps

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require(self, plan_id: str) -> AdaptiveExecutionPlan:
        plan = self._store.get(plan_id)
        if plan is None:
            raise KeyError(f"Unknown plan_id={plan_id}")
        return plan

    def _parse_steps(
        self, steps: Sequence[PlanStep | dict[str, Any]]
    ) -> list[PlanStep]:
        out: list[PlanStep] = []
        for i, s in enumerate(steps or []):
            if isinstance(s, PlanStep):
                out.append(s)
            elif isinstance(s, dict):
                if not s.get("step_id"):
                    s = dict(s)
                    s["step_id"] = f"s{i + 1}"
                out.append(PlanStep.from_dict(s))
            else:
                raise TypeError("steps must be PlanStep or dict")
        return out

    def _re_id_steps(self, steps: list[PlanStep], prefix: str) -> list[PlanStep]:
        id_map = {s.step_id: f"{prefix}_{s.step_id}" for s in steps}
        out = []
        for s in steps:
            ns = PlanStep.from_dict(s.to_dict())
            ns.step_id = id_map.get(s.step_id, s.step_id)
            ns.depends_on = [id_map.get(d, d) for d in s.depends_on]
            ns.status = StepStatus.PENDING
            out.append(ns)
        return out


def _tool_to_step_type(tool_id: str) -> StepType:
    t = (tool_id or "").lower()
    if t in {"forecast"}:
        return StepType.FORECAST
    if t in {"visualization", "scatter_plot", "histogram", "trend"}:
        return StepType.VISUALIZE
    if t in {"correlation", "regression", "comparison", "eda_summary", "outlier_detection"}:
        return StepType.ANALYZE
    return StepType.CUSTOM


def _flag_in_result(obs: StepObservation, *flags: str) -> bool:
    if obs.error:
        err = obs.error.lower()
        for f in flags:
            if f.lower() in err:
                return True
    result = obs.result or {}
    status = str(result.get("status") or result.get("retrieval_status") or "").lower()
    for f in flags:
        fl = f.lower()
        if status == fl or result.get(fl) is True:
            return True
        if fl in status:
            return True
    meta = obs.metadata or {}
    for f in flags:
        if meta.get(f) is True:
            return True
    return False


# ---------------------------------------------------------------------------
# Module façade
# ---------------------------------------------------------------------------

_default_planner: AdaptivePlanner | None = None


def get_adaptive_planner() -> AdaptivePlanner:
    global _default_planner
    if _default_planner is None:
        _default_planner = AdaptivePlanner()
    return _default_planner


def reset_adaptive_planner() -> None:
    global _default_planner
    from backend.adaptive_planning.state import reset_default_store

    _default_planner = None
    reset_default_store()


def create_adaptive_plan(
    question: str,
    steps: Sequence[PlanStep | dict[str, Any]] | None = None,
    **kwargs: Any,
) -> AdaptiveExecutionPlan:
    return get_adaptive_planner().create_plan(question, steps, **kwargs)
