"""Dynamic Tool Selection Agent.

Given user question + DatasetProfile + Conversation Context → ExecutionPlan.

Does not modify Planner, EDA, Visualization, or existing analytical tools.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.tool_selection.models import (
    ExecutionPlan,
    SelectedTool,
    Tool,
    ToolSelectionInput,
    ToolSpec,
)
from backend.tool_selection.prompts import build_tool_selection_prompt
from backend.tool_selection.registry import ToolRegistry, get_default_registry

logger = get_logger(__name__)

_STOP = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by",
    "from", "please", "me", "my", "our", "is", "are", "be", "as", "at", "into",
}


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 1 and t not in _STOP
    }


def extract_profile_signals(profile: Optional[dict[str, Any]]) -> list[str]:
    """Derive coarse signals from a DatasetProfile-like dict."""
    if not profile:
        return []
    signals: list[str] = []
    dtype = str(profile.get("dataset_type") or "").lower()
    if dtype:
        signals.append(dtype)
    if profile.get("time_column"):
        signals.append("time")
    if dtype == "time_series" or profile.get("time_column"):
        signals.append("time_series")
    numeric = profile.get("numeric_metrics") or []
    if isinstance(numeric, list):
        if len(numeric) >= 1:
            signals.append("numeric_metric")
        if len(numeric) >= 2:
            signals.append("multi_numeric")
    cats = profile.get("categorical_fields") or []
    if isinstance(cats, list) and len(cats) >= 1:
        signals.append("categorical")
    if profile.get("entity_column"):
        signals.append("entity")
    row_count = profile.get("row_count") or 0
    try:
        if int(row_count) >= 500:
            signals.append("large_n")
    except (TypeError, ValueError):
        pass
    # multi metric via column names
    cols = profile.get("column_names") or []
    if isinstance(cols, list) and len(cols) >= 3:
        signals.append("multi_metric")
    return list(dict.fromkeys(signals))


def extract_context_hints(context: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not context:
        return {}
    hints: dict[str, Any] = {}
    for key in (
        "last_operation",
        "last_intent",
        "last_forecast_target",
        "metrics",
        "selected_countries",
        "last_columns",
    ):
        if context.get(key) is not None:
            hints[key] = context.get(key)
    if context.get("filters"):
        hints["has_filters"] = True
    return hints


def check_requirements(
    spec: ToolSpec,
    profile: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
) -> bool:
    """
    Return False only when hard requirements are clearly unmet.

    Missing profile → do not block (unknown dataset shape).
    """
    if not spec.requires:
        return True
    if not profile:
        return True  # unknown profile: allow selection by question alone
    signals = set(extract_profile_signals(profile))
    for req in spec.requires:
        if req not in signals:
            # Soft: if requires multi_numeric but we only know numeric_metric, allow
            if req == "multi_numeric" and "numeric_metric" in signals:
                continue
            if req == "categorical" and "entity" in signals:
                continue
            return False
    return True


def default_tool_score(
    spec: ToolSpec,
    question: str,
    profile: Optional[dict[str, Any]] = None,
    context: Optional[dict[str, Any]] = None,
) -> float:
    """Keyword + intent + profile preference scoring in [0, 1]."""
    if not spec.enabled:
        return 0.0

    q = (question or "").lower()
    q_tokens = _tokens(question)
    score = 0.0

    # Keyword hits (phrase first, then tokens)
    kw_hits = 0
    for kw in spec.keywords:
        kw_l = kw.lower()
        if " " in kw_l:
            if kw_l in q:
                kw_hits += 2
        elif kw_l in q_tokens or re.search(rf"\b{re.escape(kw_l)}\b", q):
            kw_hits += 1
    if kw_hits:
        score += min(0.55, 0.18 * kw_hits)

    # Intent string overlap with question / context
    ctx_intent = ""
    if context:
        ctx_intent = str(context.get("last_intent") or context.get("last_operation") or "").lower()
    for intent in spec.intents:
        intent_l = intent.lower().replace("_", " ")
        if intent_l in q or intent.replace("_", "") in q.replace(" ", ""):
            score += 0.12
        if ctx_intent and (intent in ctx_intent or intent_l in ctx_intent):
            score += 0.08

    # Profile prefers / requires
    signals = set(extract_profile_signals(profile))
    if spec.requires:
        if all(
            r in signals
            or (r == "multi_numeric" and "numeric_metric" in signals)
            or (r == "categorical" and "entity" in signals)
            for r in spec.requires
        ):
            score += 0.12
        elif profile and not check_requirements(spec, profile, context):
            return 0.0

    prefer_hits = sum(1 for p in spec.prefers if p in signals)
    if prefer_hits:
        score += min(0.2, 0.08 * prefer_hits)

    # Context boosts
    if context:
        last_op = str(context.get("last_operation") or "").lower()
        if last_op and any(last_op in (i or "") for i in spec.intents):
            score += 0.05
        if context.get("last_forecast_target") and spec.tool_id in {
            "forecast",
            "trend",
            "time_series",
        }:
            score += 0.08
        metrics = context.get("metrics") or []
        if metrics and spec.tool_id in {
            "trend",
            "forecast",
            "visualization",
            "distribution",
        }:
            score += 0.04

    # Mild prior for general tools on vague questions
    if not kw_hits and spec.tool_id == "eda_summary" and len(q_tokens) <= 6:
        score += 0.2
    if not kw_hits and spec.tool_id == "visualization" and any(
        t in q_tokens for t in ("show", "plot", "chart", "graph", "display")
    ):
        score += 0.35

    return float(max(0.0, min(1.0, score)))


class ToolSelector(ABC):
    """Select analytical tools for a user question."""

    name: str = "base"

    @abstractmethod
    def select(self, selection_input: ToolSelectionInput) -> ExecutionPlan:
        ...

    def select_tools(
        self,
        question: str,
        profile: Any = None,
        context: Any = None,
        **kwargs: Any,
    ) -> ExecutionPlan:
        """Primary API (Planner will call this later)."""
        return self.select(
            ToolSelectionInput.from_raw(question, profile, context, **kwargs)
        )


class RuleBasedToolSelector(ToolSelector):
    """
    Deterministic tool selection using registry + keyword/profile scoring.

    Default production selector — no LLM required.
    """

    name = "rule_based"

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        *,
        max_tools: int = 6,
        min_score: float = 0.25,
    ):
        self._registry = registry or get_default_registry()
        self.max_tools = max_tools
        self.min_score = min_score

    def select(self, selection_input: ToolSelectionInput) -> ExecutionPlan:
        question = selection_input.question or ""
        profile = selection_input.profile
        context = selection_input.context
        max_tools = selection_input.max_tools or self.max_tools
        min_score = (
            selection_input.min_score
            if selection_input.min_score is not None
            else self.min_score
        )

        signals = extract_profile_signals(profile)
        hints = extract_context_hints(context)
        warnings: list[str] = []

        if not question.strip():
            return ExecutionPlan(
                question=question,
                selected_tools=[],
                reason="Empty question.",
                confidence=0.0,
                selector=self.name,
                profile_signals=signals,
                context_hints=hints,
                warnings=["Empty question"],
            )

        scored: list[tuple[Tool, float, str]] = []
        all_scored: list[tuple[Tool, float, str]] = []
        score_map: dict[str, float] = {}

        for tool in self._registry.list_tools(enabled_only=True):
            spec = tool.spec
            if not check_requirements(spec, profile, context):
                score_map[spec.tool_id] = 0.0
                continue
            s = tool.score(question, profile, context)
            score_map[spec.tool_id] = round(s, 4)
            reason = _reason_for(spec, question, s, signals)
            all_scored.append((tool, s, reason))
            if s >= min_score:
                scored.append((tool, s, reason))

        # Sort by score desc, then priority asc
        scored.sort(key=lambda x: (-x[1], x[0].spec.priority, x[0].spec.tool_id))
        all_scored.sort(key=lambda x: (-x[1], x[0].spec.priority, x[0].spec.tool_id))

        # Apply domain co-selection heuristics (companions may be below min_score)
        selected = _apply_co_selection(
            scored,
            question=question,
            profile=profile,
            max_tools=max_tools,
            include_visualization=selection_input.include_visualization,
            catalog=all_scored,
        )

        if not selected:
            # Fallback: EDA summary if registered
            eda = self._registry.get("eda_summary")
            if eda and eda.spec.enabled:
                selected = [
                    SelectedTool(
                        tool_id=eda.spec.tool_id,
                        name=eda.spec.name,
                        category=eda.spec.category.value,
                        score=0.3,
                        reason="Fallback exploratory analysis for underspecified question.",
                        produces_chart=eda.spec.produces_chart,
                        order=1,
                        tags=list(eda.spec.tags),
                    )
                ]
                warnings.append("No strong tool match; defaulted to EDA summary.")
            else:
                warnings.append("No tools matched the question.")

        conf = _plan_confidence(selected)
        reason = _plan_reason(question, selected)

        plan = ExecutionPlan(
            question=question,
            selected_tools=selected,
            reason=reason,
            confidence=conf,
            selector=self.name,
            profile_signals=signals,
            context_hints=hints,
            scores=score_map,
            warnings=warnings,
        )
        logger.info(
            "Tool selection complete",
            extra={
                "tools": plan.tool_ids,
                "confidence": conf,
                "question": question[:80],
            },
        )
        return plan


class LLMToolSelector(ToolSelector):
    """
    Optional LLM-backed selector.

    Falls back to RuleBasedToolSelector when LLM is disabled or fails.
    Does not replace the default rule-based path.
    """

    name = "llm"

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        *,
        fallback: ToolSelector | None = None,
    ):
        self._registry = registry or get_default_registry()
        self._fallback = fallback or RuleBasedToolSelector(registry=self._registry)

    def select(self, selection_input: ToolSelectionInput) -> ExecutionPlan:
        # Prefer deterministic path unless explicitly using LLM path successfully
        try:
            from backend.config import settings

            use_llm = bool(getattr(settings, "USE_LLM_INTENT", False))
        except Exception:
            use_llm = False

        if not use_llm:
            plan = self._fallback.select(selection_input)
            plan.selector = f"{self.name}+{plan.selector}"
            plan.metadata["llm_used"] = False
            return plan

        tools = [t.spec.to_dict() for t in self._registry.list_tools()]
        prompt = build_tool_selection_prompt(
            selection_input.question,
            tools,
            profile=selection_input.profile,
            context=selection_input.context,
        )
        try:
            from backend.llm.ollama_client import invoke_llm

            raw = invoke_llm(prompt)
            parsed = _parse_llm_selection(raw)
            if not parsed or not parsed.get("selected_tool_ids"):
                raise ValueError("LLM returned no tool ids")

            selected: list[SelectedTool] = []
            for i, tid in enumerate(parsed["selected_tool_ids"]):
                tool = self._registry.get(str(tid))
                if not tool:
                    continue
                selected.append(
                    SelectedTool(
                        tool_id=tool.spec.tool_id,
                        name=tool.spec.name,
                        category=tool.spec.category.value,
                        score=max(0.0, min(1.0, float(parsed.get("confidence") or 0.7))),
                        reason=str(parsed.get("reason") or "Selected by LLM"),
                        produces_chart=tool.spec.produces_chart,
                        order=i + 1,
                        tags=list(tool.spec.tags),
                    )
                )
            if not selected:
                raise ValueError("No registered tools matched LLM ids")

            return ExecutionPlan(
                question=selection_input.question,
                selected_tools=selected,
                reason=str(parsed.get("reason") or "LLM tool selection"),
                confidence=float(parsed.get("confidence") or 0.7),
                selector=self.name,
                profile_signals=extract_profile_signals(selection_input.profile),
                context_hints=extract_context_hints(selection_input.context),
                metadata={"llm_used": True},
            )
        except Exception as exc:
            logger.warning("LLM tool selection failed; using fallback", extra={"error": str(exc)})
            plan = self._fallback.select(selection_input)
            plan.warnings.append(f"LLM selection failed: {exc}")
            plan.selector = f"{self.name}_fallback+{plan.selector}"
            plan.metadata["llm_used"] = False
            return plan


# ---------------------------------------------------------------------------
# Co-selection heuristics (question patterns → companion tools)
# ---------------------------------------------------------------------------


def _apply_co_selection(
    scored: list[tuple[Tool, float, str]],
    *,
    question: str,
    profile: Optional[dict[str, Any]],
    max_tools: int,
    include_visualization: bool,
    catalog: list[tuple[Tool, float, str]] | None = None,
) -> list[SelectedTool]:
    """
    Build ordered selection from top scores + question-pattern companion tools.

    ``catalog`` includes all applicable tools (even below min_score) so companions
    like trend/visualization can be co-selected for forecast questions.
    """
    if not scored and not catalog:
        return []

    q = (question or "").lower()
    # Full catalog for companion lookup; scored for primary ranking
    pool = catalog if catalog is not None else scored
    by_id = {t.spec.tool_id: (t, s, r) for t, s, r in pool}
    ordered_ids: list[str] = []

    def _add(tid: str) -> None:
        if tid in by_id and tid not in ordered_ids:
            ordered_ids.append(tid)

    # Seed with top scored (or best in catalog)
    seed_list = scored if scored else pool
    seed_list = sorted(seed_list, key=lambda x: (-x[1], x[0].spec.priority))
    if seed_list:
        _add(seed_list[0][0].spec.tool_id)

    # Pattern bundles — companions pulled from full catalog
    if _matches_forecast(q):
        for tid in ("forecast", "trend", "time_series", "visualization"):
            _add(tid)
    if _matches_relationship(q):
        for tid in ("correlation", "regression", "scatter_plot", "visualization"):
            _add(tid)
    if _matches_outlier(q):
        for tid in ("outlier_detection", "histogram", "distribution", "visualization"):
            _add(tid)
    if _matches_seasonality(q):
        for tid in ("seasonality", "time_series", "trend", "visualization"):
            _add(tid)
    if _matches_cluster(q):
        for tid in ("clustering", "pca", "visualization"):
            _add(tid)
    if _matches_hypothesis(q):
        for tid in ("hypothesis_testing", "anova", "comparison"):
            _add(tid)
    if _matches_distribution(q):
        for tid in ("distribution", "histogram", "visualization"):
            _add(tid)

    # Fill remaining by score among tools that passed min_score
    for tool, _s, _r in seed_list:
        _add(tool.spec.tool_id)
        if len(ordered_ids) >= max_tools:
            break

    # Ensure visualization companion when useful
    if include_visualization and "visualization" in by_id:
        has_chart = any(
            by_id[tid][0].spec.produces_chart for tid in ordered_ids if tid in by_id
        )
        if not has_chart and any(
            tid in ordered_ids
            for tid in ("forecast", "trend", "correlation", "outlier_detection")
        ):
            _add("visualization")

    ordered_ids = ordered_ids[:max_tools]

    selected: list[SelectedTool] = []
    for i, tid in enumerate(ordered_ids):
        tool, s, reason = by_id[tid]
        # Co-selected companions may be slightly below min_score
        display_score = s if s >= 0.15 else max(s, 0.28)
        # Annotate co-selected low scorers
        if s < 0.25 and "co-selected" not in reason.lower():
            reason = f"{reason}; co-selected as companion tool"
        selected.append(
            SelectedTool(
                tool_id=tool.spec.tool_id,
                name=tool.spec.name,
                category=tool.spec.category.value
                if hasattr(tool.spec.category, "value")
                else str(tool.spec.category),
                score=round(display_score, 4),
                reason=reason,
                produces_chart=tool.spec.produces_chart,
                order=i + 1,
                tags=list(tool.spec.tags),
            )
        )
    return selected


def _matches_forecast(q: str) -> bool:
    return bool(
        re.search(
            r"\b(forecast|predict|prediction|next\s+\d+|future|projection)\b", q
        )
    )


def _matches_relationship(q: str) -> bool:
    return bool(
        re.search(
            r"\b(relationship|correlation|correlate|regression|associated|association)\b",
            q,
        )
        or re.search(r"\bbetween\b.+\band\b", q)
    )


def _matches_outlier(q: str) -> bool:
    return bool(
        re.search(
            r"\b(outlier|anomaly|anomalies|unusual|abnormal|extreme values|strange)\b",
            q,
        )
    )


def _matches_seasonality(q: str) -> bool:
    return bool(re.search(r"\b(seasonality|seasonal|periodic|cycle)\b", q))


def _matches_cluster(q: str) -> bool:
    return bool(re.search(r"\b(cluster|clustering|segment|segmentation|k-?means)\b", q))


def _matches_hypothesis(q: str) -> bool:
    return bool(
        re.search(
            r"\b(hypothesis|significant|significance|p-?value|t-?test|anova|chi-?square)\b",
            q,
        )
    )


def _matches_distribution(q: str) -> bool:
    return bool(re.search(r"\b(distribution|histogram|density|spread|skew)\b", q))


def _reason_for(
    spec: ToolSpec, question: str, score: float, signals: list[str]
) -> str:
    parts = [f"Matched '{spec.name}' (score={score:.2f})"]
    q = (question or "").lower()
    hit_kws = [kw for kw in spec.keywords if kw.lower() in q]
    if hit_kws:
        parts.append("keywords: " + ", ".join(hit_kws[:4]))
    pref = [p for p in spec.prefers if p in signals]
    if pref:
        parts.append("profile: " + ", ".join(pref))
    return "; ".join(parts)


def _plan_confidence(selected: list[SelectedTool]) -> float:
    if not selected:
        return 0.0
    top = selected[0].score
    avg = sum(t.score for t in selected) / len(selected)
    return round(max(0.0, min(1.0, 0.6 * top + 0.4 * avg)), 4)


def _plan_reason(question: str, selected: list[SelectedTool]) -> str:
    if not selected:
        return "No analytical tools selected."
    names = ", ".join(t.name for t in selected)
    return f"For '{question[:120]}' selected: {names}."


def _parse_llm_selection(response: str) -> Optional[dict[str, Any]]:
    if not response:
        return None
    text = response.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Extract JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_default_selector: ToolSelector | None = None


def get_default_selector() -> ToolSelector:
    global _default_selector
    if _default_selector is None:
        _default_selector = RuleBasedToolSelector()
    return _default_selector


def set_default_selector(selector: ToolSelector) -> None:
    global _default_selector
    _default_selector = selector


def reset_default_selector() -> None:
    global _default_selector
    _default_selector = None


def select_tools(
    question: str,
    profile: Any = None,
    context: Any = None,
    **kwargs: Any,
) -> ExecutionPlan:
    """
    Module-level entrypoint.

    Planner will later call this; not integrated into the graph yet.
    """
    return get_default_selector().select_tools(
        question, profile=profile, context=context, **kwargs
    )
