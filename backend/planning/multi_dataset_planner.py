"""Multi-dataset planner — detect multiple required datasets (planning only).

Does not call Retrieval, Acquisition, or LangGraph execution.
Produces a list of DatasetRequest for a later loop.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.planning.models import MultiDatasetIntent, MultiDatasetPlan
from backend.retrieval.models import DatasetRequest

logger = get_logger(__name__)

# Canonical metrics → preferred retrieval topic labels
METRIC_CATALOG: list[tuple[str, str, tuple[str, ...]]] = [
    # (canonical_id, display_topic, aliases)
    ("gdp", "GDP", ("gdp", "gross domestic product", "economic growth", "economy size")),
    ("population", "population", ("population", "demographics", "people count", "inhabitants")),
    ("inflation", "inflation", ("inflation", "cpi", "consumer price", "price index")),
    ("co2", "CO2 emissions", ("co2", "co₂", "carbon", "emissions", "carbon dioxide", "ghg")),
    ("unemployment", "unemployment", ("unemployment", "jobless", "joblessness")),
    ("gold", "gold price", ("gold", "gold price", "gold rate", "bullion", "xau")),
    ("temperature", "temperature", ("temperature", "global temp", "warming")),
    ("climate", "climate", ("climate", "climate change")),
    ("covid", "covid", ("covid", "coronavirus", "pandemic")),
    ("stock", "stock market", ("stock", "s&p", "equity market", "share prices")),
    ("oil", "oil price", ("oil", "crude", "brent", "wti")),
    ("energy", "energy", ("energy", "electricity", "power generation")),
    ("revenue", "revenue", ("revenue", "sales revenue")),
    ("sales", "sales", ("sales", "retail sales")),
]

COUNTRY_PATTERNS: list[tuple[str, str]] = [
    (r"\bindia\b", "India"),
    (r"\bchina\b", "China"),
    (r"\bunited states\b|\busa\b|\b\bus\b", "United States"),
    (r"\bunited kingdom\b|\buk\b", "United Kingdom"),
    (r"\bjapan\b", "Japan"),
    (r"\bgermany\b", "Germany"),
    (r"\bbrazil\b", "Brazil"),
    (r"\bcanada\b", "Canada"),
    (r"\bfrance\b", "France"),
    (r"\baustralia\b", "Australia"),
]


class MultiDatasetPlanner:
    """
    Identify one or more DatasetRequest objects from a natural-language question.

    Examples:
      "Compare India GDP, Population, Inflation, CO2 emissions"
        → 4 DatasetRequest topics
      "Analyze India GDP"
        → 1 DatasetRequest (preserves single-dataset behavior)
    """

    def plan(
        self,
        question: str,
        *,
        session_id: Optional[str] = None,
        force_new_topic: bool = True,
    ) -> MultiDatasetPlan:
        q = (question or "").strip()
        if not q:
            return MultiDatasetPlan(
                requests=[],
                intent=MultiDatasetIntent.SINGLE,
                question=q,
                is_multi=False,
                notes=["Empty question."],
            )

        normalized = q.lower()
        intent = self._detect_intent(normalized)
        metrics = self._detect_metrics(normalized)
        entities = self._detect_entities(normalized)

        # Build topics: metric (+ optional primary entity prefix for country-specific series)
        primary_entity = entities[0] if entities else None
        topics = self._build_topics(metrics, primary_entity, q, intent)

        if not topics:
            # Single-dataset fallback: use cleaned question / residual phrase
            topics = [self._fallback_single_topic(q, normalized)]

        requests = [
            DatasetRequest(
                topic=topic,
                session_id=session_id,
                question=q,
                force_new_topic=force_new_topic,
            )
            for topic in topics
        ]

        # Dedupe by normalized topic while preserving order
        seen: set[str] = set()
        unique_requests: list[DatasetRequest] = []
        unique_metrics: list[str] = []
        for req, metric in zip(requests, metrics or [None] * len(requests)):
            key = req.normalized_topic().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique_requests.append(req)
            if metric:
                unique_metrics.append(metric)

        if not unique_metrics and metrics:
            unique_metrics = metrics

        is_multi = len(unique_requests) > 1
        if is_multi and intent == MultiDatasetIntent.SINGLE:
            intent = MultiDatasetIntent.MULTI_METRIC

        notes = []
        if is_multi:
            notes.append(f"Detected {len(unique_requests)} dataset requests.")
        if entities:
            notes.append(f"Entities: {', '.join(entities)}.")

        plan = MultiDatasetPlan(
            requests=unique_requests,
            intent=intent,
            metrics=unique_metrics or [r.topic for r in unique_requests],
            entities=entities,
            question=q,
            is_multi=is_multi,
            notes=notes,
        )
        logger.info(
            "Multi-dataset plan created",
            extra={
                "intent": plan.intent.value,
                "n_requests": len(plan.requests),
                "topics": plan.topics(),
            },
        )
        return plan

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def _detect_intent(self, normalized: str) -> MultiDatasetIntent:
        if any(
            k in normalized
            for k in (
                "compare",
                "comparison",
                "versus",
                " vs ",
                "vs.",
                "against",
                "difference between",
            )
        ):
            return MultiDatasetIntent.COMPARISON
        if any(
            k in normalized
            for k in (
                "correlation",
                "correlate",
                "correlated",
                "relationship between",
                "related to",
                "heatmap",
            )
        ):
            return MultiDatasetIntent.CORRELATION
        if any(
            k in normalized
            for k in (
                "forecast",
                "predict",
                "projection",
                "future",
                "next year",
                "next years",
                "for the next",
            )
        ):
            return MultiDatasetIntent.FORECASTING
        return MultiDatasetIntent.SINGLE

    def _detect_metrics(self, normalized: str) -> list[str]:
        found: list[str] = []
        # Longer aliases first to avoid partial traps
        catalog = sorted(METRIC_CATALOG, key=lambda x: -max(len(a) for a in x[2]))
        for canonical, _display, aliases in catalog:
            for alias in sorted(aliases, key=len, reverse=True):
                if alias in normalized:
                    if canonical not in found:
                        found.append(canonical)
                    break
        # Split on commas / "and" for free-form multi lists after known metrics
        # e.g. "GDP, Population, Inflation and CO2"
        return found

    def _detect_entities(self, normalized: str) -> list[str]:
        found: list[str] = []
        for pattern, label in COUNTRY_PATTERNS:
            if re.search(pattern, normalized):
                if label not in found:
                    found.append(label)
        return found

    def _build_topics(
        self,
        metrics: list[str],
        primary_entity: Optional[str],
        question: str,
        intent: MultiDatasetIntent,
    ) -> list[str]:
        if not metrics:
            return []

        display_map = {canonical: display for canonical, display, _ in METRIC_CATALOG}
        topics: list[str] = []
        for m in metrics:
            label = display_map.get(m, m)
            # For country-scoped compares / single-country multi-metric, prefix entity
            if primary_entity and intent in {
                MultiDatasetIntent.COMPARISON,
                MultiDatasetIntent.CORRELATION,
                MultiDatasetIntent.MULTI_METRIC,
                MultiDatasetIntent.FORECASTING,
                MultiDatasetIntent.SINGLE,
            }:
                # "India GDP" style when entity present and metric is national
                if m in {
                    "gdp",
                    "population",
                    "inflation",
                    "co2",
                    "unemployment",
                    "energy",
                }:
                    topics.append(f"{primary_entity} {label}")
                else:
                    topics.append(label)
            else:
                topics.append(label)
        return topics

    def _fallback_single_topic(self, question: str, normalized: str) -> str:
        # Strip common verbs for a residual topic phrase
        cleaned = re.sub(
            r"\b(analyze|analyse|compare|correlation|correlate|forecast|predict|"
            r"show|plot|study|explore|the|a|an|of|for|between|and|vs|versus|"
            r"relationship|next|\d+\s*years?)\b",
            " ",
            normalized,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[^a-z0-9\s\-]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            return cleaned
        return question.strip()[:80]


def plan_dataset_requests(
    question: str,
    *,
    session_id: Optional[str] = None,
    force_new_topic: bool = True,
) -> list[DatasetRequest]:
    """Return list[DatasetRequest] — primary planning API for LangGraph later."""
    plan = MultiDatasetPlanner().plan(
        question,
        session_id=session_id,
        force_new_topic=force_new_topic,
    )
    return plan.requests


def plan_multi_dataset(
    question: str,
    *,
    session_id: Optional[str] = None,
    force_new_topic: bool = True,
) -> MultiDatasetPlan:
    """Return full MultiDatasetPlan (requests + intent metadata)."""
    return MultiDatasetPlanner().plan(
        question,
        session_id=session_id,
        force_new_topic=force_new_topic,
    )
