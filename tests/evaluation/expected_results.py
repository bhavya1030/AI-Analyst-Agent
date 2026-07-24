"""Soft expected results and scoring helpers for evaluation cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tests.evaluation.test_cases import EvalTestCase


@dataclass
class ExpectationScore:
    """Partial credit scoring for one case (0–1 per dimension)."""

    retrieval: Optional[float] = None
    selection: Optional[float] = None
    semantic: Optional[float] = None
    planner: Optional[float] = None
    context: Optional[float] = None
    join: Optional[float] = None
    forecast: Optional[float] = None
    chart: Optional[float] = None
    explanation: Optional[float] = None
    failure_recovery: Optional[float] = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "retrieval": self.retrieval,
            "selection": self.selection,
            "semantic": self.semantic,
            "planner": self.planner,
            "context": self.context,
            "join": self.join,
            "forecast": self.forecast,
            "chart": self.chart,
            "explanation": self.explanation,
            "failure_recovery": self.failure_recovery,
            "notes": list(self.notes),
        }

    def mean(self) -> float:
        vals = [
            v
            for v in (
                self.retrieval,
                self.selection,
                self.semantic,
                self.planner,
                self.context,
                self.join,
                self.forecast,
                self.chart,
                self.explanation,
                self.failure_recovery,
            )
            if v is not None
        ]
        if not vals:
            return 0.0
        return sum(vals) / len(vals)


def score_case(case: EvalTestCase, record: dict[str, Any]) -> ExpectationScore:
    """
    Score a completed evaluation record against soft expectations.

    Does not hard-fail the suite — scores feed the metrics report.
    """
    score = ExpectationScore()
    status = str(record.get("status") or "")
    errors = record.get("errors") or []
    warnings = record.get("warnings") or []
    retrieved = record.get("retrieved_datasets") or []
    planner = record.get("planner_output") or {}
    tools = record.get("selected_tools") or []
    tool_ids = [
        (t.get("tool_id") if isinstance(t, dict) else str(t)) for t in tools
    ]
    explanation = record.get("explanation") or {}
    context_resolution = record.get("context_resolution") or {}

    topics_blob = " ".join(
        str(x.get("topic") if isinstance(x, dict) else x) for x in retrieved
    ).lower()
    planner_topics = " ".join(str(t) for t in (planner.get("topics") or [])).lower()
    combined_topics = topics_blob + " " + planner_topics

    # --- Retrieval ---
    if case.expect_intent == "discovery":
        # Discovery: any non-crash retrieval/search attempt is partial success
        if record.get("retrieval_status") and record.get("retrieval_status") != "ERROR":
            score.retrieval = 0.7
            if retrieved or record.get("retrieval_status") in {
                "SEARCH_REQUIRED",
                "API_HIT",
                "INTERNET_HIT",
                "REGISTRY_HIT",
                "SEMANTIC_HIT",
            }:
                score.retrieval = 1.0
        else:
            score.retrieval = 0.0 if errors else 0.3
    elif case.expect_graceful_failure or case.expect_intent == "edge":
        # Edge: success = graceful handling (error message / warning / stop) without crash
        if record.get("crashed"):
            score.failure_recovery = 0.0
            score.retrieval = 0.0
        elif errors or warnings or record.get("graceful_failure"):
            score.failure_recovery = 1.0
            score.retrieval = 0.8
        else:
            # Completed without claiming impossible success is ok
            score.failure_recovery = 0.7
            score.retrieval = 0.5
    else:
        if retrieved or planner.get("topics"):
            score.retrieval = 0.6
            # Metric/entity soft match
            hits = 0
            need = list(case.expect_metrics) + list(case.expect_entities)
            if need:
                for n in need:
                    if n.lower() in combined_topics or n.lower() in case.question.lower():
                        # entity in question always true — check topic presence for metrics
                        if n in case.expect_metrics:
                            if n.lower().split()[0] in combined_topics:
                                hits += 1
                        else:
                            hits += 1
                score.retrieval = min(1.0, 0.4 + 0.6 * (hits / max(1, len(need))))
            else:
                score.retrieval = 0.8 if retrieved or planner.get("topics") else 0.3
        else:
            score.retrieval = 0.2 if status == "passed" else 0.0

    # --- Selection / semantic (from record flags) ---
    if record.get("selection_ok") is True:
        score.selection = 1.0
    elif record.get("selection_ok") is False:
        score.selection = 0.0
    if record.get("semantic_score") is not None:
        try:
            score.semantic = max(0.0, min(1.0, float(record["semantic_score"])))
        except (TypeError, ValueError):
            score.semantic = None

    # --- Planner ---
    if case.expect_multi_dataset or case.expect_intent in {
        "comparison",
        "correlation",
    }:
        n_topics = len(planner.get("topics") or planner.get("requests") or [])
        if n_topics >= 2:
            score.planner = 1.0
        elif n_topics == 1:
            score.planner = 0.4
            score.notes.append("Expected multi-dataset plan, got single topic")
        else:
            score.planner = 0.0
    elif case.expect_intent == "forecast":
        tools_l = " ".join(str(t).lower() for t in tool_ids)
        plan_intent = str(planner.get("intent") or planner.get("objective_type") or "").lower()
        if "forecast" in tools_l or "forecast" in plan_intent or "forecast" in case.question.lower():
            score.planner = 1.0 if ("forecast" in tools_l or "forecast" in plan_intent) else 0.7
        else:
            score.planner = 0.3
    elif planner or tools:
        score.planner = 0.8
    else:
        score.planner = 0.4 if case.expect_intent in {"stress", "edge", "explain"} else 0.2

    # --- Context ---
    if case.category.startswith("6_") or "followup" in case.tags:
        if context_resolution.get("is_follow_up") or context_resolution.get("resolved_question"):
            score.context = 1.0 if context_resolution.get("resolved_question") else 0.6
        elif case.id == 51:
            score.context = 1.0  # opening turn
        elif case.id == 60:
            score.context = 1.0 if record.get("context_cleared") else 0.5
        else:
            score.context = 0.3
    elif context_resolution:
        score.context = 0.8

    # --- Join ---
    join = record.get("join_plan") or {}
    if case.expect_multi_dataset:
        if join.get("strategy") or join.get("join_keys"):
            score.join = 1.0
        elif len(planner.get("topics") or []) >= 2:
            score.join = 0.5  # planned multi but join not executed
        else:
            score.join = 0.0
    elif join:
        score.join = 0.8

    # --- Forecast ---
    if case.expect_intent == "forecast" or "forecast" in case.question.lower():
        if any("forecast" in str(t).lower() for t in tool_ids) or record.get("forecast_ran"):
            score.forecast = 1.0
        else:
            score.forecast = 0.3

    # --- Chart ---
    charts = record.get("generated_charts") or []
    if charts:
        score.chart = 1.0
    elif any(
        (isinstance(t, dict) and t.get("produces_chart"))
        or str(t).lower() in {"visualization", "trend", "scatter_plot", "histogram"}
        for t in tools
    ):
        score.chart = 0.5  # planned viz tool but chart not materialized in eval mode
    elif case.expect_intent in {"analysis", "comparison", "forecast"}:
        score.chart = 0.2

    # --- Explanation ---
    if case.expect_explanation or case.expect_intent == "explain":
        if explanation and (
            explanation.get("explanation_text")
            or explanation.get("reasoning_summary")
            or explanation.get("summary")
        ):
            score.explanation = 1.0
            # Tag-specific soft checks
            text = (
                str(explanation.get("explanation_text") or "")
                + str(explanation.get("detailed_text") or "")
                + str(explanation.get("technical_text") or "")
            ).lower()
            tag_needles = {
                "dataset_choice": ["dataset", "source"],
                "reasoning": ["reason"],
                "joins": ["join"],
                "confidence": ["confidence"],
                "limitations": ["limitation"],
                "filters": ["filter"],
                "columns": ["column"],
                "tools": ["tool"],
                "citations": ["citation", "["],
                "technical": ["technical", "strategy=", "tools"],
            }
            for tag in case.tags:
                needles = tag_needles.get(tag)
                if needles and not any(n in text for n in needles):
                    score.explanation = min(score.explanation, 0.6)
                    score.notes.append(f"Explanation weak for tag={tag}")
        else:
            score.explanation = 0.0
    elif explanation:
        score.explanation = 0.8

    # Crash always tanks failure recovery
    if record.get("crashed") and score.failure_recovery is None:
        score.failure_recovery = 0.0
    elif not record.get("crashed") and case.expect_intent == "stress":
        score.failure_recovery = 1.0 if status in {"passed", "warning"} else 0.4

    return score


def overall_pass(case: EvalTestCase, record: dict[str, Any], score: ExpectationScore) -> str:
    """
    Return status: passed | warning | failed.

    - crashed → failed
    - edge graceful → passed if recovered
    - mean score thresholds
    """
    if record.get("crashed"):
        return "failed"
    if case.expect_graceful_failure or case.expect_intent == "edge":
        if score.failure_recovery is not None and score.failure_recovery >= 0.7:
            return "passed"
        if record.get("errors") and not record.get("crashed"):
            return "passed"
        return "warning"

    mean = score.mean()
    if mean >= 0.55 and not (record.get("errors") and case.expect_intent not in {"edge", "stress"}):
        # soft errors ok for discovery
        if record.get("errors") and case.expect_intent not in {"discovery", "stress", "explain", "followup"}:
            if mean >= 0.7:
                return "warning"
            return "failed"
        return "passed"
    if mean >= 0.35:
        return "warning"
    return "failed"
