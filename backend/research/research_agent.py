"""Autonomous Research Agent — plans multi-dataset research (no execution).

Receives user question + conversation context and returns ResearchPlan.
Does NOT retrieve datasets or modify the existing Planner.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.research.models import (
    DatasetNecessity,
    DatasetPriority,
    DatasetRequirement,
    ResearchInput,
    ResearchObjective,
    ResearchObjectiveType,
    ResearchPlan,
)
from backend.research.planner import ResearchPlanner
from backend.research.prompts import build_research_plan_prompt

logger = get_logger(__name__)


class AutonomousResearchAgent:
    """
    High-level research planning agent.

    Workflow:
      question + context
        → determine research objective
        → expand required datasets / goals / dependencies
        → ResearchPlan

    Execution (retrieval, join, EDA) is intentionally out of scope.
    """

    def __init__(self, planner: ResearchPlanner | None = None):
        self._planner = planner or ResearchPlanner()

    def plan_research(
        self,
        question: str,
        context: Any = None,
        **kwargs: Any,
    ) -> ResearchPlan:
        """Primary API: produce a ResearchPlan for a broad analytical question."""
        research_input = ResearchInput.from_raw(question, context=context, **kwargs)
        plan = self._planner.plan(research_input)
        logger.info(
            "AutonomousResearchAgent plan ready",
            extra={
                "objective": plan.objective.objective_type.value
                if isinstance(plan.objective.objective_type, ResearchObjectiveType)
                else plan.objective.objective_type,
                "topics": plan.topics,
                "mandatory": plan.mandatory_topics,
            },
        )
        return plan

    def plan(self, research_input: ResearchInput | str, **kwargs: Any) -> ResearchPlan:
        """Alias supporting ResearchInput or raw question string."""
        if isinstance(research_input, ResearchInput):
            return self._planner.plan(research_input)
        return self.plan_research(research_input, **kwargs)

    # Convenience accessors for future graph nodes
    def required_topics(self, question: str, context: Any = None) -> list[str]:
        return self.plan_research(question, context=context).topics

    def mandatory_topics(self, question: str, context: Any = None) -> list[str]:
        return self.plan_research(question, context=context).mandatory_topics


class LLMResearchAgent(AutonomousResearchAgent):
    """
    Optional LLM-assisted research planning.

    Falls back to rule-based ResearchPlanner when LLM is disabled or fails.
    """

    def __init__(self, planner: ResearchPlanner | None = None):
        super().__init__(planner=planner)

    def plan_research(
        self,
        question: str,
        context: Any = None,
        **kwargs: Any,
    ) -> ResearchPlan:
        try:
            from backend.config import settings

            use_llm = bool(getattr(settings, "USE_LLM_PLANNER", False))
        except Exception:
            use_llm = False

        if not use_llm:
            plan = super().plan_research(question, context=context, **kwargs)
            plan.metadata["llm_used"] = False
            return plan

        research_input = ResearchInput.from_raw(question, context=context, **kwargs)
        prompt = build_research_plan_prompt(
            research_input.question,
            context=research_input.context,
        )
        try:
            from backend.llm.ollama_client import invoke_llm

            raw = invoke_llm(prompt)
            parsed = _parse_llm_plan(raw)
            if not parsed or not parsed.get("datasets"):
                raise ValueError("LLM returned no datasets")
            plan = _plan_from_llm_payload(research_input.question, parsed)
            plan.planner = "llm"
            plan.context_used = bool(research_input.context)
            plan.metadata["llm_used"] = True
            return plan
        except Exception as exc:
            logger.warning(
                "LLM research planning failed; using rule-based planner",
                extra={"error": str(exc)},
            )
            plan = super().plan_research(question, context=context, **kwargs)
            plan.warnings.append(f"LLM research planning failed: {exc}")
            plan.metadata["llm_used"] = False
            plan.planner = f"llm_fallback+{plan.planner}"
            return plan


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_default_agent: AutonomousResearchAgent | None = None


def get_research_agent() -> AutonomousResearchAgent:
    global _default_agent
    if _default_agent is None:
        _default_agent = AutonomousResearchAgent()
    return _default_agent


def set_research_agent(agent: AutonomousResearchAgent) -> None:
    global _default_agent
    _default_agent = agent


def reset_research_agent() -> None:
    global _default_agent
    _default_agent = None


def plan_research(
    question: str,
    context: Any = None,
    **kwargs: Any,
) -> ResearchPlan:
    """Module-level entrypoint for autonomous research planning."""
    return get_research_agent().plan_research(question, context=context, **kwargs)


# ---------------------------------------------------------------------------
# LLM payload helpers
# ---------------------------------------------------------------------------


def _parse_llm_plan(response: str) -> Optional[dict[str, Any]]:
    if not response:
        return None
    text = response.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _plan_from_llm_payload(question: str, payload: dict[str, Any]) -> ResearchPlan:
    ot_raw = str(payload.get("objective_type") or "exploration")
    try:
        ot = ResearchObjectiveType(ot_raw)
    except ValueError:
        ot = ResearchObjectiveType.EXPLORATION

    objective = ResearchObjective(
        objective_type=ot,
        summary=str(payload.get("objective_summary") or ""),
        primary_metric=str(payload.get("primary_metric") or ""),
        entities=[str(e) for e in (payload.get("entities") or [])],
        secondary_metrics=[str(m) for m in (payload.get("secondary_metrics") or [])],
    )

    datasets: list[DatasetRequirement] = []
    for i, d in enumerate(payload.get("datasets") or []):
        if not isinstance(d, dict):
            continue
        pr = d.get("priority") or "medium"
        try:
            priority = DatasetPriority(str(pr))
        except ValueError:
            priority = DatasetPriority.MEDIUM
        nec = d.get("necessity") or "optional"
        try:
            necessity = DatasetNecessity(str(nec))
        except ValueError:
            necessity = DatasetNecessity.OPTIONAL
        topic = str(d.get("topic") or "").strip()
        if not topic:
            continue
        datasets.append(
            DatasetRequirement(
                topic=topic,
                reason=str(d.get("reason") or ""),
                priority=priority,
                necessity=necessity,
                role=str(d.get("role") or "context"),
                depends_on=[str(x) for x in (d.get("depends_on") or [])],
                entities=[str(e) for e in (d.get("entities") or objective.entities)],
                order=i + 1,
            )
        )

    # Reuse rule planner helpers for goals/outputs if LLM omitted them
    base = ResearchPlanner().plan(question)
    goals = base.analysis_goals
    outputs = base.expected_outputs
    if payload.get("analysis_goals"):
        from backend.research.models import AnalysisGoal

        goals = [
            AnalysisGoal.from_dict(g) if isinstance(g, dict) else g
            for g in payload["analysis_goals"]
        ]
    if payload.get("expected_outputs"):
        from backend.research.models import ExpectedOutput

        outputs = [
            ExpectedOutput.from_dict(o) if isinstance(o, dict) else o
            for o in payload["expected_outputs"]
        ]

    deps = []
    for d in datasets:
        for dep in d.depends_on:
            deps.append({"from": dep, "to": d.topic})

    return ResearchPlan(
        question=question,
        objective=objective,
        required_datasets=datasets,
        analysis_goals=goals,
        expected_outputs=outputs,
        dependencies=deps,
        confidence=float(payload.get("confidence") or 0.7),
        planner="llm",
    )
