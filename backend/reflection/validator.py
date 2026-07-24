"""Rule-based validators for reflection checks.

Each check returns a list of ReflectionIssue (may be empty).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from backend.reflection.models import (
    IssueCategory,
    IssueSeverity,
    ReflectionInput,
    ReflectionIssue,
)

# Claims that often indicate overreach / hallucination
_ABSOLUTE_CLAIM_PATTERNS = [
    r"\bproves?\b",
    r"\bcauses?\b",
    r"\bcaused\b",
    r"\bdefinitely\b",
    r"\balways\b",
    r"\bnever\b",
    r"\bguaranteed\b",
    r"\bwith certainty\b",
    r"\bno doubt\b",
    r"\b100%\s*certain\b",
]

_IMPOSSIBLE_PATTERNS = [
    r"\bnegative population\b",
    r"\bpopulation of\s*-?\d+\b",
    r"\bgdp growth of\s*1000\s*%",
    r"\binflation of\s*-?9\d{2,}\s*%",
    r"\b1000\s*%\s*(growth|increase|inflation)",
    r"\bunemployment of\s*1[5-9]\d\s*%",  # >150% unemployment absurd
    r"\bunemployment of\s*[2-9]\d{2,}\s*%",
]

# Question topic tokens → expected dataset topic tokens
_TOPIC_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("gdp", ("gdp", "gross domestic", "economy")),
    ("inflation", ("inflation", "cpi", "price")),
    ("population", ("population", "demographic")),
    ("gold", ("gold", "xau", "bullion")),
    ("oil", ("oil", "crude", "brent", "wti")),
    ("rainfall", ("rain", "precip", "monsoon")),
    ("unemployment", ("unemployment", "jobless", "employment")),
    ("co2", ("co2", "carbon", "emission")),
    ("bitcoin", ("bitcoin", "btc", "crypto")),
]


class ReflectionValidator:
    """Run all quality checks against a ReflectionInput package."""

    def validate_all(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        issues.extend(self.check_dataset_correctness(inp))
        issues.extend(self.check_reasoning_consistency(inp))
        issues.extend(self.check_confidence(inp))
        issues.extend(self.check_citations(inp))
        issues.extend(self.check_visualization(inp))
        issues.extend(self.check_joins(inp))
        issues.extend(self.check_statistical_sanity(inp))
        issues.extend(self.check_hallucinations(inp))
        return issues

    # ------------------------------------------------------------------
    # 1. Dataset correctness
    # ------------------------------------------------------------------

    def check_dataset_correctness(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        datasets = list(inp.datasets_used or [])
        question = (inp.question or "").lower()

        if not datasets:
            issues.append(
                ReflectionIssue(
                    code="no_datasets",
                    message="No datasets recorded for this analysis.",
                    category=IssueCategory.DATASET,
                    severity=IssueSeverity.ERROR,
                    recommendation="Retrieve or attach at least one relevant dataset before answering.",
                )
            )
            return issues

        topics = " ".join(
            str(d.get("topic") or d.get("title") or d.get("name") or "") for d in datasets
        ).lower()
        sources = [
            str(d.get("source") or d.get("provider") or "") for d in datasets if d.get("source") or d.get("provider")
        ]

        # Topic mismatch: question metric not reflected in dataset topics
        for metric, aliases in _TOPIC_HINTS:
            if metric in question or any(a in question for a in aliases):
                if not any(a in topics or metric in topics for a in aliases):
                    # Allow if question metric appears in answer columns
                    cols = " ".join(
                        str(c)
                        for d in datasets
                        for c in (d.get("columns") or d.get("column_names") or [])
                    ).lower()
                    if not any(a in cols or metric in cols for a in aliases):
                        issues.append(
                            ReflectionIssue(
                                code="dataset_topic_mismatch",
                                message=f"Question references '{metric}' but datasets may not match.",
                                category=IssueCategory.DATASET,
                                severity=IssueSeverity.WARNING,
                                evidence=f"datasets topics: {topics[:200]}",
                                recommendation=f"Verify the active dataset covers {metric} or retrieve a better match.",
                            )
                        )
                        break

        # Planetary / nonsense entities
        if re.search(r"\b(mars|jupiter|saturn|venus|pluto)\b", question):
            issues.append(
                ReflectionIssue(
                    code="implausible_entity",
                    message="Question references a non-terrestrial entity; terrestrial datasets are likely inappropriate.",
                    category=IssueCategory.DATASET,
                    severity=IssueSeverity.ERROR,
                    recommendation="Refuse or clearly qualify that no valid dataset exists for this subject.",
                )
            )

        # Missing provenance
        if not sources and not any(d.get("source_url") or d.get("download_url") for d in datasets):
            issues.append(
                ReflectionIssue(
                    code="missing_dataset_source",
                    message="Datasets lack source / provider metadata.",
                    category=IssueCategory.DATASET,
                    severity=IssueSeverity.WARNING,
                    recommendation="Attach source metadata (registry, World Bank, upload path, etc.).",
                )
            )

        return issues

    # ------------------------------------------------------------------
    # 2. Reasoning consistency
    # ------------------------------------------------------------------

    def check_reasoning_consistency(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        answer = _answer_text(inp)
        explanation = _explanation_text(inp)
        if not answer and not explanation:
            issues.append(
                ReflectionIssue(
                    code="empty_analysis",
                    message="No analysis answer or explanation text to validate.",
                    category=IssueCategory.REASONING,
                    severity=IssueSeverity.WARNING,
                    recommendation="Produce an answer with supporting explanation before delivery.",
                )
            )
            return issues

        # Comparison question without multi-dataset or compare language in tools
        q = (inp.question or "").lower()
        if re.search(r"\b(compare|versus|vs\.?)\b", q):
            n_ds = len(inp.datasets_used or [])
            tools = _tool_ids(inp)
            if n_ds < 2 and "comparison" not in tools and "compare" not in answer.lower():
                issues.append(
                    ReflectionIssue(
                        code="comparison_incomplete",
                        message="Comparison question but weak multi-entity evidence in results.",
                        category=IssueCategory.REASONING,
                        severity=IssueSeverity.WARNING,
                        evidence=f"n_datasets={n_ds}, tools={tools}",
                        recommendation="Load both sides of the comparison or run the comparison tool.",
                    )
                )

        # Forecast question without forecast tool / horizon
        if re.search(r"\b(forecast|predict|projection)\b", q):
            tools = _tool_ids(inp)
            if "forecast" not in tools and "forecast" not in answer.lower():
                issues.append(
                    ReflectionIssue(
                        code="forecast_not_executed",
                        message="Forecasting intent detected but forecast step not evidenced.",
                        category=IssueCategory.REASONING,
                        severity=IssueSeverity.WARNING,
                        recommendation="Run the forecast tool or qualify that no forecast was produced.",
                    )
                )

        # Answer contradicts explanation confidence language
        if "cannot" in answer.lower() and "confident" in answer.lower():
            issues.append(
                ReflectionIssue(
                    code="self_contradiction",
                    message="Answer language appears self-contradictory.",
                    category=IssueCategory.REASONING,
                    severity=IssueSeverity.WARNING,
                    recommendation="Rewrite the answer for consistent tone and claims.",
                )
            )

        return issues

    # ------------------------------------------------------------------
    # 3. Confidence validation
    # ------------------------------------------------------------------

    def check_confidence(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        conf = _extract_confidence(inp)
        if conf is None:
            return issues

        strong_evidence = _has_strong_evidence(inp)
        n_ds = len(inp.datasets_used or [])
        has_citations = _has_citations(inp)
        has_explanation = bool(_explanation_text(inp))

        if conf >= 0.85 and not strong_evidence:
            issues.append(
                ReflectionIssue(
                    code="overconfident",
                    message=f"Reported confidence ({conf:.2f}) is high without strong evidence.",
                    category=IssueCategory.CONFIDENCE,
                    severity=IssueSeverity.ERROR,
                    evidence=f"datasets={n_ds}, citations={has_citations}, explanation={has_explanation}",
                    recommendation="Lower confidence or strengthen evidence (sources, citations, methodology).",
                )
            )
        elif conf >= 0.7 and n_ds == 0:
            issues.append(
                ReflectionIssue(
                    code="confidence_without_data",
                    message="Confidence is elevated but no datasets are attached.",
                    category=IssueCategory.CONFIDENCE,
                    severity=IssueSeverity.ERROR,
                    recommendation="Do not report high confidence without data backing.",
                )
            )
        elif conf >= 0.75 and not has_citations and not has_explanation:
            issues.append(
                ReflectionIssue(
                    code="confidence_without_trace",
                    message="Moderate-high confidence without citations or explanation.",
                    category=IssueCategory.CONFIDENCE,
                    severity=IssueSeverity.WARNING,
                    recommendation="Attach explanation and citations before presenting confidence.",
                )
            )

        # Explicit overconfidence language in answer with low structural evidence
        answer = _answer_text(inp).lower()
        if re.search(r"\b(certain|definitely|guaranteed|100%)\b", answer) and conf is not None and conf < 0.9:
            # absolute language even if confidence field not that high
            if not strong_evidence:
                issues.append(
                    ReflectionIssue(
                        code="absolute_language",
                        message="Answer uses absolute certainty language without matching evidence.",
                        category=IssueCategory.CONFIDENCE,
                        severity=IssueSeverity.WARNING,
                        recommendation="Soften claims (e.g. 'suggests', 'is consistent with').",
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # 4. Missing citations
    # ------------------------------------------------------------------

    def check_citations(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        answer = _answer_text(inp)
        if not answer or len(answer) < 40:
            return issues

        has_citations = _has_citations(inp)
        has_numeric_claim = bool(
            re.search(r"\b\d+(\.\d+)?\s*%|\b\d{4}\b|\$\s*\d|\b\d+(\.\d+)?\s*(billion|million|trillion)\b", answer)
        )
        major_conclusion = len(answer) > 80 or has_numeric_claim

        if major_conclusion and not has_citations:
            # datasets with source count as weak citation
            weak = any(
                d.get("source") or d.get("source_url") or d.get("provider") or d.get("dataset_id")
                for d in (inp.datasets_used or [])
            )
            if not weak:
                issues.append(
                    ReflectionIssue(
                        code="missing_citations",
                        message="Major conclusions lack citations or dataset evidence links.",
                        category=IssueCategory.CITATIONS,
                        severity=IssueSeverity.WARNING,
                        recommendation="Cite dataset sources and key figures used in the conclusion.",
                    )
                )
            else:
                issues.append(
                    ReflectionIssue(
                        code="citations_not_surface",
                        message="Dataset sources exist but were not surfaced as citations in the explanation.",
                        category=IssueCategory.CITATIONS,
                        severity=IssueSeverity.INFO,
                        recommendation="Expose citation labels in the user-facing explanation.",
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # 5. Visualization review
    # ------------------------------------------------------------------

    def check_visualization(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        charts = list(inp.charts or [])
        q = (inp.question or "").lower()
        tools = _tool_ids(inp)

        # Infer chart types from charts or tools
        chart_types = []
        for c in charts:
            ct = str(c.get("chart_type") or c.get("type") or c.get("kind") or "").lower()
            if ct:
                chart_types.append(ct)
            if c.get("planned") and c.get("tool_id"):
                chart_types.append(str(c["tool_id"]).lower())

        # Forecast / trend questions prefer line charts
        if re.search(r"\b(forecast|trend|over time|time series)\b", q):
            if chart_types and not any(
                t in {"line", "trend", "timeseries", "time_series", "forecast", "area"}
                for t in chart_types
            ):
                if any(t in {"pie", "donut"} for t in chart_types):
                    issues.append(
                        ReflectionIssue(
                            code="bad_chart_for_trend",
                            message="Pie/donut chart is a poor fit for trend/forecast questions.",
                            category=IssueCategory.VISUALIZATION,
                            severity=IssueSeverity.WARNING,
                            evidence=f"chart_types={chart_types}",
                            recommendation="Prefer a line chart (or multi-line) for time trends and forecasts.",
                        )
                    )
            if not charts and "visualization" not in tools and "trend" not in tools:
                issues.append(
                    ReflectionIssue(
                        code="missing_trend_chart",
                        message="Trend/forecast question without a visualization step.",
                        category=IssueCategory.VISUALIZATION,
                        severity=IssueSeverity.INFO,
                        recommendation="Add a line chart of the primary metric over time.",
                    )
                )

        # Correlation / relationship → scatter preferred
        if re.search(r"\b(relationship|correlation|vs\.?|versus)\b", q):
            if chart_types and not any(
                t in {"scatter", "scatter_plot", "heatmap", "correlation"} for t in chart_types
            ):
                if any(t in {"pie", "bar"} for t in chart_types) and "line" not in chart_types:
                    issues.append(
                        ReflectionIssue(
                            code="bad_chart_for_correlation",
                            message="Chart type may not best show bivariate relationships.",
                            category=IssueCategory.VISUALIZATION,
                            severity=IssueSeverity.INFO,
                            recommendation="Prefer scatter plot or correlation heatmap.",
                        )
                    )

        # Comparison of categories → bar preferred over pie for many categories
        for c in charts:
            n_cats = c.get("n_categories") or c.get("category_count")
            ct = str(c.get("chart_type") or c.get("type") or "").lower()
            try:
                if n_cats is not None and int(n_cats) > 6 and ct in {"pie", "donut"}:
                    issues.append(
                        ReflectionIssue(
                            code="pie_too_many_slices",
                            message="Pie chart with many categories is hard to read.",
                            category=IssueCategory.VISUALIZATION,
                            severity=IssueSeverity.WARNING,
                            recommendation="Use a sorted bar chart for many categories.",
                        )
                    )
            except (TypeError, ValueError):
                pass

        return issues

    # ------------------------------------------------------------------
    # 6. Join validation
    # ------------------------------------------------------------------

    def check_joins(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        join = inp.join_plan or {}
        n_ds = len(inp.datasets_used or [])
        if n_ds < 2 and not join:
            return issues

        strategy = str(join.get("strategy") or join.get("join_strategy") or "").lower()
        keys = join.get("join_keys") or []
        if isinstance(keys, str):
            keys = [keys]

        if n_ds >= 2:
            if not strategy and not keys:
                issues.append(
                    ReflectionIssue(
                        code="join_unspecified",
                        message="Multiple datasets used but join strategy/keys are missing.",
                        category=IssueCategory.JOIN,
                        severity=IssueSeverity.WARNING,
                        recommendation="Document join strategy (e.g. outer on Country+Year) or concat rationale.",
                    )
                )
            if strategy == "concat" and keys:
                issues.append(
                    ReflectionIssue(
                        code="join_concat_with_keys",
                        message="Concat used despite join keys being present — may lose alignment.",
                        category=IssueCategory.JOIN,
                        severity=IssueSeverity.INFO,
                        evidence=f"strategy={strategy}, keys={keys}",
                        recommendation="Prefer keyed join when shared entity/time columns exist.",
                    )
                )
            if strategy in {"inner", "left", "outer", "right"} and not keys:
                issues.append(
                    ReflectionIssue(
                        code="join_missing_keys",
                        message=f"{strategy} join specified without join keys.",
                        category=IssueCategory.JOIN,
                        severity=IssueSeverity.ERROR,
                        recommendation="Provide join keys (e.g. Country, Year) or fall back to explicit concat.",
                    )
                )

            # Suspicious keys
            for k in keys:
                kl = str(k).lower()
                if kl in {"value", "amount", "price", "gdp", "index"}:
                    issues.append(
                        ReflectionIssue(
                            code="suspicious_join_key",
                            message=f"Joining on metric column '{k}' is usually incorrect.",
                            category=IssueCategory.JOIN,
                            severity=IssueSeverity.ERROR,
                            recommendation="Join on entity/time keys (Country, Year, Date), not metric values.",
                        )
                    )

        notes = " ".join(str(n) for n in (join.get("notes") or join.get("warnings") or [])).lower()
        if "incompatible" in notes or "fallback" in notes:
            issues.append(
                ReflectionIssue(
                    code="join_fallback",
                    message="Join plan notes indicate schema incompatibility or fallback merge.",
                    category=IssueCategory.JOIN,
                    severity=IssueSeverity.WARNING,
                    evidence=notes[:200],
                    recommendation="Review aligned columns; avoid interpreting concat as a true relational join.",
                )
            )

        return issues

    # ------------------------------------------------------------------
    # 7. Statistical sanity
    # ------------------------------------------------------------------

    def check_statistical_sanity(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        text = (_answer_text(inp) + " " + _explanation_text(inp)).lower()
        if not text.strip():
            return issues

        for pat in _IMPOSSIBLE_PATTERNS:
            if re.search(pat, text, flags=re.I):
                issues.append(
                    ReflectionIssue(
                        code="impossible_statistic",
                        message="Answer contains a statistically implausible claim.",
                        category=IssueCategory.STATISTICAL,
                        severity=IssueSeverity.CRITICAL,
                        evidence=pat,
                        recommendation="Remove or recompute the figure; verify units and filters.",
                    )
                )
                break

        # Percentage > 100 for rates that should be bounded (rough)
        for m in re.finditer(
            r"(unemployment|literacy|market share|probability)[^\d%]{0,40}(\d{3,})(\.\d+)?\s*%",
            text,
            flags=re.I,
        ):
            try:
                val = float(m.group(2))
                if val > 100:
                    issues.append(
                        ReflectionIssue(
                            code="rate_over_100",
                            message=f"Bounded rate appears >100% ({m.group(0)}).",
                            category=IssueCategory.STATISTICAL,
                            severity=IssueSeverity.ERROR,
                            recommendation="Check percentage scale and data units.",
                        )
                    )
            except ValueError:
                pass

        # Growth of thousands of percent without caveats
        if re.search(r"\b(grew|increased|rose)\b[^\.]{0,40}\b(\d{3,})\s*%", text):
            if "base" not in text and "from a low" not in text:
                issues.append(
                    ReflectionIssue(
                        code="extreme_growth_claim",
                        message="Extreme percentage growth claim without base-effect caveat.",
                        category=IssueCategory.STATISTICAL,
                        severity=IssueSeverity.WARNING,
                        recommendation="Add base period context or verify the calculation.",
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # 8. Hallucination detection
    # ------------------------------------------------------------------

    def check_hallucinations(self, inp: ReflectionInput) -> list[ReflectionIssue]:
        issues: list[ReflectionIssue] = []
        answer = _answer_text(inp)
        if not answer:
            return issues

        # Named entities / metrics in answer not present in datasets or question
        ds_blob = " ".join(
            str(d.get("topic") or "")
            + " "
            + " ".join(str(c) for c in (d.get("columns") or d.get("column_names") or []))
            for d in (inp.datasets_used or [])
        ).lower()
        q = (inp.question or "").lower()
        context_blob = ""
        if inp.conversation_context:
            context_blob = " ".join(
                str(x)
                for x in (
                    inp.conversation_context.get("metrics") or [],
                    inp.conversation_context.get("selected_countries") or [],
                    [
                        (d.get("topic") if isinstance(d, dict) else "")
                        for d in (inp.conversation_context.get("active_datasets") or [])
                    ],
                )
            ).lower()

        # Specific fabricated source patterns
        if re.search(r"\baccording to (the )?(secret|internal|classified)\b", answer, re.I):
            issues.append(
                ReflectionIssue(
                    code="unverifiable_source",
                    message="Answer cites an unverifiable or secret source.",
                    category=IssueCategory.HALLUCINATION,
                    severity=IssueSeverity.ERROR,
                    recommendation="Only cite available dataset metadata sources.",
                )
            )

        # Absolute causal claims
        for pat in _ABSOLUTE_CLAIM_PATTERNS:
            if re.search(pat, answer, flags=re.I):
                # causal "causes" is more severe
                sev = (
                    IssueSeverity.ERROR
                    if "cause" in pat
                    else IssueSeverity.WARNING
                )
                issues.append(
                    ReflectionIssue(
                        code="unsupported_absolute_claim",
                        message="Answer contains absolute/causal language that may be unsupported.",
                        category=IssueCategory.HALLUCINATION,
                        severity=sev,
                        evidence=pat,
                        recommendation="Rephrase as association/correlation unless causal design is established.",
                    )
                )
                break

        # Numeric claims with no datasets at all
        if re.search(r"\b\d+(\.\d+)?\s*%", answer) and not (inp.datasets_used or []):
            issues.append(
                ReflectionIssue(
                    code="numeric_without_data",
                    message="Numeric claims present without any attached datasets.",
                    category=IssueCategory.HALLUCINATION,
                    severity=IssueSeverity.ERROR,
                    recommendation="Ground numbers in retrieved data or remove them.",
                )
            )

        # Country named in answer but nowhere in question/datasets/context
        countries = re.findall(
            r"\b(India|China|Brazil|Japan|Germany|France|Canada|Australia|Mexico|Russia)\b",
            answer,
        )
        for c in countries:
            cl = c.lower()
            if cl not in q and cl not in ds_blob and cl not in context_blob:
                issues.append(
                    ReflectionIssue(
                        code="unanchored_entity",
                        message=f"Answer mentions '{c}' without clear grounding in question or datasets.",
                        category=IssueCategory.HALLUCINATION,
                        severity=IssueSeverity.WARNING,
                        recommendation="Remove unanchored entities or attach supporting data.",
                    )
                )
                break

        return issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _answer_text(inp: ReflectionInput) -> str:
    ar = inp.analysis_result or {}
    for key in ("answer", "summary", "insight", "text", "result"):
        val = ar.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    insights = ar.get("insights")
    if isinstance(insights, list) and insights:
        first = insights[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(first.get("summary") or first.get("text") or first)
    return ""


def _explanation_text(inp: ReflectionInput) -> str:
    er = inp.explanation_result or {}
    parts = [
        er.get("explanation_text"),
        er.get("reasoning_summary"),
        er.get("summary"),
        er.get("detailed_text"),
        er.get("short_text"),
    ]
    return " ".join(str(p) for p in parts if p)


def _extract_confidence(inp: ReflectionInput) -> Optional[float]:
    for blob in (inp.analysis_result, inp.explanation_result, inp.execution_plan):
        if not blob:
            continue
        if blob.get("confidence") is not None:
            try:
                return float(blob["confidence"])
            except (TypeError, ValueError):
                pass
        if blob.get("adjusted_confidence") is not None:
            try:
                return float(blob["adjusted_confidence"])
            except (TypeError, ValueError):
                pass
    return None


def _has_citations(inp: ReflectionInput) -> bool:
    er = inp.explanation_result or {}
    citations = er.get("citations") or er.get("sources") or []
    if citations:
        return True
    text = _explanation_text(inp) + " " + _answer_text(inp)
    if re.search(r"\[\d+\]|source:|according to", text, flags=re.I):
        return True
    return False


def _has_strong_evidence(inp: ReflectionInput) -> bool:
    n_ds = len(inp.datasets_used or [])
    has_src = any(
        d.get("source") or d.get("source_url") or d.get("provider") or d.get("local_path")
        for d in (inp.datasets_used or [])
    )
    has_cit = _has_citations(inp)
    has_expl = bool(_explanation_text(inp))
    tools = _tool_ids(inp)
    return n_ds >= 1 and has_src and (has_cit or has_expl) and (bool(tools) or n_ds >= 2)


def _tool_ids(inp: ReflectionInput) -> list[str]:
    plan = inp.execution_plan or {}
    tools = plan.get("selected_tools") or plan.get("tools") or plan.get("tool_ids") or []
    out: list[str] = []
    for t in tools:
        if isinstance(t, dict):
            out.append(str(t.get("tool_id") or t.get("name") or "").lower())
        else:
            out.append(str(t).lower())
    ar = inp.analysis_result or {}
    for t in ar.get("tools_executed") or ar.get("plan") or []:
        if isinstance(t, dict):
            out.append(str(t.get("tool_id") or t.get("name") or "").lower())
        else:
            out.append(str(t).lower())
    return [x for x in out if x]
