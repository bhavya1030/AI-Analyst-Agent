"""Reflection / Self-Correction Agent.

Reviews analytical packages before user delivery.
Does not modify Planner, Retrieval, Acquisition, Execution, Viz, or Explainability.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.reflection.models import (
    CorrectedPlan,
    IssueSeverity,
    ReflectionInput,
    ReflectionIssue,
    ReflectionResult,
)
from backend.reflection.prompts import build_reflection_prompt
from backend.reflection.validator import ReflectionValidator, _extract_confidence

logger = get_logger(__name__)

_SEVERITY_RANK = {
    IssueSeverity.INFO: 0,
    IssueSeverity.WARNING: 1,
    IssueSeverity.ERROR: 2,
    IssueSeverity.CRITICAL: 3,
}


class ReflectionAgent(ABC):
    """Review analysis quality and recommend corrections."""

    name: str = "base"

    @abstractmethod
    def reflect(self, reflection_input: ReflectionInput) -> ReflectionResult:
        ...

    def review(
        self,
        *,
        question: str = "",
        conversation_context: Any = None,
        execution_plan: Any = None,
        analysis_result: Any = None,
        explanation_result: Any = None,
        charts: Any = None,
        datasets_used: Any = None,
        join_plan: Any = None,
        **kwargs: Any,
    ) -> ReflectionResult:
        """Primary API — stable when swapping RuleBased → LLM."""
        inp = ReflectionInput.from_raw(
            question=question,
            conversation_context=conversation_context,
            execution_plan=execution_plan,
            analysis_result=analysis_result,
            explanation_result=explanation_result,
            charts=charts,
            datasets_used=datasets_used,
            join_plan=join_plan,
            metadata=kwargs.get("metadata"),
        )
        return self.reflect(inp)


class RuleBasedReflection(ReflectionAgent):
    """
    Deterministic reflection using ReflectionValidator.

    Behavior:
      - no issues / only INFO → approved
      - WARNING only → approved=True with issues attached (warnings path)
      - ERROR/CRITICAL → approved=False + corrected_plan for re-run
    """

    name = "rule_based"

    def __init__(self, validator: ReflectionValidator | None = None):
        self._validator = validator or ReflectionValidator()

    def reflect(self, reflection_input: ReflectionInput) -> ReflectionResult:
        inp = reflection_input
        issues = self._validator.validate_all(inp)
        max_sev = _max_severity(issues)
        original_conf = _extract_confidence(inp)
        adjustment = _confidence_delta(issues, original_conf)
        adjusted = None
        if original_conf is not None:
            adjusted = max(0.0, min(1.0, original_conf + adjustment))

        severe = max_sev in {IssueSeverity.ERROR, IssueSeverity.CRITICAL}
        has_warn = max_sev in {
            IssueSeverity.WARNING,
            IssueSeverity.ERROR,
            IssueSeverity.CRITICAL,
        }

        # approved: True when no severe issues (warnings still approved with flags)
        approved = not severe

        corrected = None
        if severe:
            corrected = _build_corrected_plan(inp, issues)
        elif has_warn:
            # Soft corrected plan notes without forcing re-run
            corrected = _build_corrected_plan(inp, issues, soft=True)

        recommendations = _collect_recommendations(issues)
        summary = _build_summary(approved, issues, max_sev, adjustment)

        result = ReflectionResult(
            approved=approved,
            issues=issues,
            severity=max_sev,
            recommendations=recommendations,
            corrected_plan=corrected,
            confidence_adjustment=adjustment,
            original_confidence=original_conf,
            adjusted_confidence=adjusted,
            summary=summary,
            reflector=self.name,
            question=inp.question,
            metadata={
                "n_issues": len(issues),
                "n_warnings": sum(
                    1 for i in issues if i.severity == IssueSeverity.WARNING
                ),
                "n_errors": sum(
                    1
                    for i in issues
                    if i.severity in {IssueSeverity.ERROR, IssueSeverity.CRITICAL}
                ),
            },
        )
        logger.info(
            "Reflection complete",
            extra={
                "approved": approved,
                "severity": max_sev.value,
                "n_issues": len(issues),
                "confidence_adjustment": adjustment,
            },
        )
        return result


class LLMReflection(ReflectionAgent):
    """
    Optional LLM-backed reflection.

    Falls back to RuleBasedReflection when LLM is disabled or fails.
    """

    name = "llm"

    def __init__(self, fallback: ReflectionAgent | None = None):
        self._fallback = fallback or RuleBasedReflection()

    def reflect(self, reflection_input: ReflectionInput) -> ReflectionResult:
        base = self._fallback.reflect(reflection_input)

        try:
            from backend.config import settings

            use_llm = bool(
                getattr(settings, "USE_LLM_INTENT", False)
                or getattr(settings, "USE_LLM_PLANNER", False)
            )
        except Exception:
            use_llm = False

        if not use_llm:
            base.reflector = f"{self.name}+{base.reflector}"
            base.metadata["llm_used"] = False
            return base

        payload = {
            "question": reflection_input.question,
            "datasets_used": reflection_input.datasets_used,
            "execution_plan": reflection_input.execution_plan,
            "analysis_result": _shrink(reflection_input.analysis_result),
            "explanation_result": _shrink(reflection_input.explanation_result),
            "charts": reflection_input.charts,
            "join_plan": reflection_input.join_plan,
            "rule_based_result": {
                "approved": base.approved,
                "severity": base.severity.value,
                "issues": [i.to_dict() for i in base.issues],
                "confidence_adjustment": base.confidence_adjustment,
            },
        }
        prompt = build_reflection_prompt(payload)
        try:
            from backend.llm.ollama_client import invoke_llm

            raw = invoke_llm(prompt)
            parsed = _parse_llm_json(raw)
            if not parsed:
                raise ValueError("empty LLM reflection")

            # Merge LLM issues with rule-based (union by code)
            existing = {i.code for i in base.issues}
            for item in parsed.get("issues") or []:
                if not isinstance(item, dict):
                    continue
                issue = ReflectionIssue.from_dict(item)
                if issue.code not in existing:
                    base.issues.append(issue)
                    existing.add(issue.code)

            if parsed.get("recommendations"):
                for r in parsed["recommendations"]:
                    if r and str(r) not in base.recommendations:
                        base.recommendations.append(str(r))

            if parsed.get("confidence_adjustment") is not None:
                try:
                    llm_adj = float(parsed["confidence_adjustment"])
                    # Take more conservative (lower) adjustment
                    base.confidence_adjustment = min(base.confidence_adjustment, llm_adj)
                    if base.original_confidence is not None:
                        base.adjusted_confidence = max(
                            0.0,
                            min(1.0, base.original_confidence + base.confidence_adjustment),
                        )
                except (TypeError, ValueError):
                    pass

            if parsed.get("summary"):
                base.summary = str(parsed["summary"])

            # Recompute severity / approved from merged issues
            base.severity = _max_severity(base.issues)
            base.approved = base.severity not in {
                IssueSeverity.ERROR,
                IssueSeverity.CRITICAL,
            }
            if parsed.get("should_rerun") or not base.approved:
                cp = parsed.get("corrected_plan") or {}
                base.corrected_plan = CorrectedPlan(
                    should_rerun=True,
                    reason=str(parsed.get("summary") or "LLM recommended re-run"),
                    suggested_tools=[str(t) for t in (cp.get("suggested_tools") or [])],
                    suggested_datasets=[str(d) for d in (cp.get("suggested_datasets") or [])],
                    suggested_chart_types=[
                        str(c) for c in (cp.get("suggested_chart_types") or [])
                    ],
                    join_notes=[str(n) for n in (cp.get("join_notes") or [])],
                    drop_claims=[str(c) for c in (cp.get("drop_claims") or [])],
                    require_citations=True,
                    lower_confidence=base.confidence_adjustment < 0,
                )
            base.reflector = self.name
            base.metadata["llm_used"] = True
            return base
        except Exception as exc:
            logger.warning(
                "LLM reflection failed; using rule-based",
                extra={"error": str(exc)},
            )
            base.issues.append(
                ReflectionIssue(
                    code="llm_reflection_failed",
                    message=f"LLM reflection failed: {exc}",
                    severity=IssueSeverity.INFO,
                    recommendation="Rely on rule-based reflection findings.",
                )
            )
            base.reflector = f"{self.name}_fallback+{base.reflector}"
            base.metadata["llm_used"] = False
            return base


# ---------------------------------------------------------------------------
# Module API
# ---------------------------------------------------------------------------

_default_agent: ReflectionAgent | None = None


def get_reflection_agent() -> ReflectionAgent:
    global _default_agent
    if _default_agent is None:
        _default_agent = RuleBasedReflection()
    return _default_agent


def set_reflection_agent(agent: ReflectionAgent) -> None:
    global _default_agent
    _default_agent = agent


def reset_reflection_agent() -> None:
    global _default_agent
    _default_agent = None


def reflect_on_analysis(
    *,
    question: str = "",
    conversation_context: Any = None,
    execution_plan: Any = None,
    analysis_result: Any = None,
    explanation_result: Any = None,
    charts: Any = None,
    datasets_used: Any = None,
    join_plan: Any = None,
    **kwargs: Any,
) -> ReflectionResult:
    """Module-level entrypoint."""
    return get_reflection_agent().review(
        question=question,
        conversation_context=conversation_context,
        execution_plan=execution_plan,
        analysis_result=analysis_result,
        explanation_result=explanation_result,
        charts=charts,
        datasets_used=datasets_used,
        join_plan=join_plan,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _max_severity(issues: list[ReflectionIssue]) -> IssueSeverity:
    if not issues:
        return IssueSeverity.INFO
    best = IssueSeverity.INFO
    best_rank = -1
    for i in issues:
        sev = i.severity if isinstance(i.severity, IssueSeverity) else IssueSeverity.WARNING
        rank = _SEVERITY_RANK.get(sev, 1)
        if rank > best_rank:
            best_rank = rank
            best = sev
    return best


def _confidence_delta(
    issues: list[ReflectionIssue], original: Optional[float]
) -> float:
    delta = 0.0
    for i in issues:
        if i.severity == IssueSeverity.CRITICAL:
            delta -= 0.35
        elif i.severity == IssueSeverity.ERROR:
            delta -= 0.2
        elif i.severity == IssueSeverity.WARNING:
            delta -= 0.08
        elif i.severity == IssueSeverity.INFO:
            delta -= 0.02
        if i.code in {"overconfident", "confidence_without_data"}:
            delta -= 0.1
    # Clamp
    return max(-0.5, min(0.05, round(delta, 4)))


def _collect_recommendations(issues: list[ReflectionIssue]) -> list[str]:
    out: list[str] = []
    for i in issues:
        if i.recommendation and i.recommendation not in out:
            out.append(i.recommendation)
    return out


def _build_corrected_plan(
    inp: ReflectionInput,
    issues: list[ReflectionIssue],
    *,
    soft: bool = False,
) -> CorrectedPlan:
    tools: list[str] = []
    datasets: list[str] = []
    charts: list[str] = []
    join_notes: list[str] = []
    drop_claims: list[str] = []
    require_citations = False
    lower_confidence = False

    for i in issues:
        if i.category.value == "visualization_review":
            if "line" in i.recommendation.lower():
                charts.append("line")
            if "scatter" in i.recommendation.lower():
                charts.append("scatter")
            if "bar" in i.recommendation.lower():
                charts.append("bar")
            if "heatmap" in i.recommendation.lower():
                charts.append("heatmap")
        if i.category.value == "dataset_correctness":
            # Extract metric hints from message
            for metric in ("GDP", "Inflation", "Population", "Rainfall", "Gold"):
                if metric.lower() in i.message.lower() or metric.lower() in (inp.question or "").lower():
                    datasets.append(metric)
        if i.code == "forecast_not_executed":
            tools.append("forecast")
            tools.append("trend")
        if i.code == "comparison_incomplete":
            tools.append("comparison")
        if i.code in {"missing_citations", "citations_not_surface"}:
            require_citations = True
        if i.category.value in {"confidence_validation", "hallucination_detection"}:
            lower_confidence = True
        if i.category.value == "join_validation":
            join_notes.append(i.recommendation or i.message)
        if i.category.value in {"hallucination_detection", "statistical_sanity"}:
            if i.evidence:
                drop_claims.append(i.message)

    q = (inp.question or "").lower()
    if re.search(r"\bforecast\b", q) and "forecast" not in tools:
        tools.append("forecast")
    if re.search(r"\b(relationship|correlation)\b", q):
        tools.extend(["correlation", "scatter_plot"])

    # Dedupe
    def _uniq(items: list[str]) -> list[str]:
        seen = set()
        out = []
        for x in items:
            k = x.lower()
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out

    severe = any(
        i.severity in {IssueSeverity.ERROR, IssueSeverity.CRITICAL} for i in issues
    )
    return CorrectedPlan(
        should_rerun=severe and not soft,
        reason=(
            "Severe quality issues detected; re-run with corrected plan."
            if severe and not soft
            else "Soft corrections recommended; original result may be returned with warnings."
        ),
        suggested_tools=_uniq(tools),
        suggested_datasets=_uniq(datasets),
        suggested_chart_types=_uniq(charts),
        join_notes=_uniq(join_notes),
        drop_claims=_uniq(drop_claims),
        require_citations=require_citations,
        lower_confidence=lower_confidence or severe,
        metadata={"soft": soft},
    )


def _build_summary(
    approved: bool,
    issues: list[ReflectionIssue],
    severity: IssueSeverity,
    adjustment: float,
) -> str:
    if not issues:
        return "Reflection approved: no quality issues detected."
    n_w = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
    n_e = sum(
        1 for i in issues if i.severity in {IssueSeverity.ERROR, IssueSeverity.CRITICAL}
    )
    if approved and n_e == 0:
        return (
            f"Reflection approved with {n_w} warning(s) "
            f"(max severity={severity.value}, confidence_adjustment={adjustment:+.2f})."
        )
    return (
        f"Reflection rejected for delivery as-is: {n_e} severe issue(s), {n_w} warning(s) "
        f"(max severity={severity.value}, confidence_adjustment={adjustment:+.2f}). "
        "Use corrected_plan for re-execution."
    )


def _shrink(blob: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not blob:
        return blob
    out = {}
    for k, v in blob.items():
        if k in {"data", "dataframe", "merged_dataframe", "chart"}:
            continue
        if isinstance(v, str) and len(v) > 500:
            out[k] = v[:500] + "…"
        else:
            out[k] = v
    return out


def _parse_llm_json(response: str) -> Optional[dict[str, Any]]:
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
