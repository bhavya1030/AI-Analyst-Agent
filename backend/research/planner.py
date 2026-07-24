"""Research planner — expand broad questions into ResearchPlan (no retrieval)."""

from __future__ import annotations

import re
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.research.models import (
    AnalysisGoal,
    DatasetNecessity,
    DatasetPriority,
    DatasetRequirement,
    ExpectedOutput,
    ResearchInput,
    ResearchObjective,
    ResearchObjectiveType,
    ResearchPlan,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Metric / entity catalogs
# ---------------------------------------------------------------------------

# (canonical_id, display_label, aliases)
METRIC_CATALOG: list[tuple[str, str, tuple[str, ...]]] = [
    ("gdp", "GDP", ("gdp", "gross domestic product", "economic growth", "economy", "growth rate")),
    ("inflation", "Inflation", ("inflation", "cpi", "consumer price", "price index", "price rise")),
    ("population", "Population", ("population", "demographics", "inhabitants", "people")),
    ("exports", "Exports", ("exports", "export", "trade surplus", "outbound trade")),
    ("imports", "Imports", ("imports", "import", "inbound trade")),
    ("interest_rates", "Interest Rates", (
        "interest rates", "interest rate", "repo rate", "policy rate",
        "central bank rate", "borrowing cost", "monetary policy",
    )),
    ("unemployment", "Unemployment", ("unemployment", "jobless", "joblessness", "employment")),
    ("investment", "Investment", ("investment", "fdi", "capex", "capital formation", "gross fixed capital")),
    ("industrial_production", "Industrial Production", (
        "industrial production", "iip", "manufacturing output", "factory output",
    )),
    ("exchange_rate", "Exchange Rate", ("exchange rate", "fx", "currency", "rupee", "forex")),
    ("fiscal_deficit", "Fiscal Deficit", ("fiscal deficit", "budget deficit", "government deficit")),
    ("oil", "Oil Price", ("oil", "crude", "brent", "wti", "petroleum")),
    ("co2", "CO2 Emissions", ("co2", "emissions", "carbon", "ghg")),
    ("temperature", "Temperature", ("temperature", "warming", "heat")),
    ("rainfall", "Rainfall", ("rainfall", "precipitation", "monsoon")),
    ("crop_yield", "Crop Yield", ("crop yield", "agricultural yield", "harvest")),
    ("gold", "Gold Price", ("gold", "gold price", "bullion", "xau")),
    ("stock", "Stock Market", ("stock", "equity", "share market", "s&p", "nifty", "sensex")),
    ("revenue", "Revenue", ("revenue", "sales revenue", "turnover")),
    ("sales", "Sales", ("sales", "retail sales")),
    ("energy", "Energy", ("energy", "electricity", "power consumption")),
]

COUNTRY_PATTERNS: list[tuple[str, str]] = [
    (r"\bindia\b", "India"),
    (r"\bchina\b", "China"),
    (r"\bunited states\b|\busa\b|(?<![a-z])us(?![a-z])", "United States"),
    (r"\bunited kingdom\b|\buk\b", "United Kingdom"),
    (r"\bjapan\b", "Japan"),
    (r"\bgermany\b", "Germany"),
    (r"\bbrazil\b", "Brazil"),
    (r"\bcanada\b", "Canada"),
    (r"\bfrance\b", "France"),
    (r"\baustralia\b", "Australia"),
    (r"\brussia\b", "Russia"),
    (r"\bmexico\b", "Mexico"),
    (r"\bsouth korea\b|\bkorea\b", "South Korea"),
    (r"\bindonesia\b", "Indonesia"),
    (r"\bsouth africa\b", "South Africa"),
]

# Related metrics expanded by research mode + primary domain
# primary_id → list of (related_id, role, necessity, priority, reason_template)
ROOT_CAUSE_EXPANSIONS: dict[str, list[tuple[str, str, DatasetNecessity, DatasetPriority, str]]] = {
    "gdp": [
        ("inflation", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Inflation affects real growth and demand; key slowdown driver."),
        ("interest_rates", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Interest rates influence investment and consumption."),
        ("exports", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Export demand is a major component of GDP growth."),
        ("population", "control", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Population context for per-capita and labor-force interpretation."),
        ("investment", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.HIGH,
         "Investment (capex/FDI) drives medium-term growth."),
        ("unemployment", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Labor market weakness can both cause and reflect slowdown."),
        ("industrial_production", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Industrial output is a high-frequency growth proxy."),
        ("oil", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Oil prices affect import bill and inflation for many economies."),
        ("exchange_rate", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.LOW,
         "Currency moves affect trade competitiveness."),
    ],
    "inflation": [
        ("interest_rates", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Policy rates respond to and influence inflation."),
        ("oil", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Energy prices are a major inflation component."),
        ("exchange_rate", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Depreciation can pass through to import prices."),
        ("gdp", "context", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Growth conditions interact with price pressures."),
        ("food_prices", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Food prices often dominate CPI volatility."),
    ],
    "unemployment": [
        ("gdp", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Output growth is tightly linked to employment."),
        ("inflation", "context", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Phillips-curve style trade-offs."),
        ("interest_rates", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Monetary conditions affect labor demand."),
        ("industrial_production", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Sectoral output drives jobs."),
    ],
    "exports": [
        ("exchange_rate", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "FX competitiveness drives export volumes."),
        ("gdp", "context", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Partner demand and domestic capacity."),
        ("oil", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.LOW,
         "Commodity exporters sensitive to oil."),
        ("industrial_production", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Manufacturing capacity for export supply."),
    ],
    "rainfall": [
        ("crop_yield", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Rainfall directly affects agricultural output."),
        ("temperature", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Heat stress interacts with moisture."),
    ],
    "crop_yield": [
        ("rainfall", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Precipitation is a primary yield driver."),
        ("temperature", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Temperature extremes affect yields."),
    ],
    "stock": [
        ("interest_rates", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Discount rates affect valuations."),
        ("inflation", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Inflation expectations move markets."),
        ("gdp", "context", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Macro backdrop for earnings."),
        ("oil", "driver", DatasetNecessity.OPTIONAL, DatasetPriority.LOW,
         "Energy shocks hit equities."),
    ],
    "temperature": [
        ("co2", "driver", DatasetNecessity.MANDATORY, DatasetPriority.HIGH,
         "Greenhouse gases drive long-run temperature."),
        ("energy", "context", DatasetNecessity.OPTIONAL, DatasetPriority.MEDIUM,
         "Energy use correlates with emissions."),
    ],
}

IMPACT_EXPANSIONS = ROOT_CAUSE_EXPANSIONS  # same driver graphs for impact framing

BENCHMARK_DEFAULTS = ("gdp", "inflation", "population")


class ResearchPlanner:
    """
    Rule-based research planner.

    Expands a user question into required datasets, goals, dependencies,
    and expected outputs — without retrieving anything.
    """

    name = "rule_based"

    def plan(self, research_input: ResearchInput | str, **kwargs: Any) -> ResearchPlan:
        if isinstance(research_input, str):
            research_input = ResearchInput.from_raw(research_input, **kwargs)
        elif kwargs:
            # allow overrides
            if "context" in kwargs and research_input.context is None:
                research_input = ResearchInput.from_raw(
                    research_input.question,
                    context=kwargs.get("context"),
                    max_datasets=kwargs.get("max_datasets") or research_input.max_datasets,
                )

        question = research_input.question
        context = research_input.context
        max_datasets = max(1, min(int(research_input.max_datasets or 8), 12))
        warnings: list[str] = []
        notes: list[str] = []

        if not question.strip():
            return ResearchPlan(
                question=question,
                objective=ResearchObjective(
                    objective_type=ResearchObjectiveType.EXPLORATION,
                    summary="Empty question.",
                ),
                confidence=0.0,
                planner=self.name,
                warnings=["Empty question"],
            )

        q_lower = question.lower()
        entities = self._detect_entities(q_lower, context)
        metrics = self._detect_metrics(q_lower, context)
        objective_type = self._detect_objective_type(q_lower)
        time_horizon = self._detect_time_horizon(q_lower)

        primary_id, primary_label = self._pick_primary_metric(metrics, q_lower, context)
        secondary_ids = [m for m in metrics if m != primary_id]

        objective = ResearchObjective(
            objective_type=objective_type,
            summary=self._objective_summary(
                objective_type, primary_label, entities, question
            ),
            primary_metric=primary_label,
            entities=entities,
            secondary_metrics=[self._label_for(m) for m in secondary_ids],
            time_horizon=time_horizon,
        )

        # Build dataset requirements
        datasets = self._build_datasets(
            objective_type=objective_type,
            primary_id=primary_id,
            primary_label=primary_label,
            secondary_ids=secondary_ids,
            entities=entities,
            question=question,
            max_datasets=max_datasets,
            notes=notes,
        )

        # Explicit user-named secondary metrics as mandatory if comparison/correlation
        if objective_type in {
            ResearchObjectiveType.COMPARISON,
            ResearchObjectiveType.CORRELATION,
            ResearchObjectiveType.MULTI_METRIC,
        }:
            for mid in secondary_ids:
                topic = self._topic_for(mid, entities)
                if not any(d.topic.lower() == topic.lower() for d in datasets):
                    datasets.append(
                        DatasetRequirement(
                            topic=topic,
                            reason=f"Explicitly referenced metric for {objective_type.value}.",
                            priority=DatasetPriority.HIGH,
                            necessity=DatasetNecessity.MANDATORY,
                            role="secondary_metric",
                            entities=list(entities),
                        )
                    )

        # Cap and order
        datasets = self._order_and_cap(datasets, max_datasets)

        dependencies = self._build_dependency_edges(datasets)
        goals = self._build_analysis_goals(objective, datasets, entities)
        outputs = self._build_expected_outputs(objective, goals)
        confidence = self._confidence(objective, datasets, metrics)

        if not datasets:
            warnings.append("Could not infer datasets; produced empty plan.")

        plan = ResearchPlan(
            question=question,
            objective=objective,
            required_datasets=datasets,
            analysis_goals=goals,
            expected_outputs=outputs,
            dependencies=dependencies,
            confidence=confidence,
            planner=self.name,
            warnings=warnings,
            notes=notes,
            context_used=bool(context),
            metadata={
                "primary_metric_id": primary_id,
                "detected_metric_ids": metrics,
                "max_datasets": max_datasets,
            },
        )
        logger.info(
            "Research plan created",
            extra={
                "objective": objective_type.value,
                "n_datasets": len(datasets),
                "mandatory": plan.mandatory_topics,
            },
        )
        return plan

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def _detect_objective_type(self, q: str) -> ResearchObjectiveType:
        if re.search(
            r"\b(why|root cause|what caused|what is driving|drivers? of|reason for|"
            r"slowed|slowdown|decline in|drop in|fell|falling|weakness)\b",
            q,
        ):
            return ResearchObjectiveType.ROOT_CAUSE
        if re.search(r"\b(impact of|effect of|affect|influence of|consequence)\b", q):
            return ResearchObjectiveType.IMPACT
        if re.search(
            r"\b(benchmark|peer|peers|how does .+ compare|relative to|vs world|against peers)\b",
            q,
        ):
            return ResearchObjectiveType.BENCHMARKING
        if re.search(r"\b(compare|comparison|versus|vs\.?|difference between)\b", q):
            return ResearchObjectiveType.COMPARISON
        if re.search(
            r"\b(correlat|relationship between|associated with|link between)\b", q
        ):
            return ResearchObjectiveType.CORRELATION
        if re.search(
            r"\b(forecast|predict|projection|next \d+|future|outlook)\b", q
        ):
            return ResearchObjectiveType.FORECASTING
        if re.search(r"\b(trend|over time|historical|trajectory|growth path)\b", q):
            return ResearchObjectiveType.TREND
        # Multi explicit metrics without other intent
        if len(self._detect_metrics(q, None)) >= 2:
            return ResearchObjectiveType.MULTI_METRIC
        return ResearchObjectiveType.EXPLORATION

    def _detect_entities(
        self, q: str, context: Optional[dict[str, Any]]
    ) -> list[str]:
        found: list[str] = []
        for pattern, name in COUNTRY_PATTERNS:
            if re.search(pattern, q, flags=re.I):
                if name not in found:
                    found.append(name)
        if context:
            for c in context.get("selected_countries") or []:
                c = str(c).strip()
                if c and c not in found:
                    found.append(c)
            for e in context.get("entities") or []:
                e = str(e).strip()
                if e and e not in found and e[:1].isupper():
                    found.append(e)
        return found

    def _detect_metrics(
        self, q: str, context: Optional[dict[str, Any]]
    ) -> list[str]:
        found: list[str] = []
        for mid, _label, aliases in METRIC_CATALOG:
            for alias in aliases:
                if alias in q or re.search(rf"\b{re.escape(alias)}\b", q):
                    if mid not in found:
                        found.append(mid)
                    break
        if context:
            for m in context.get("metrics") or []:
                mid = self._metric_id_from_label(str(m))
                if mid and mid not in found:
                    found.append(mid)
            # Active dataset topics
            for d in context.get("active_datasets") or []:
                if isinstance(d, dict):
                    topic = str(d.get("topic") or "").lower()
                    mid = self._metric_id_from_label(topic)
                    if mid and mid not in found:
                        found.append(mid)
            target = context.get("last_forecast_target")
            if target:
                mid = self._metric_id_from_label(str(target))
                if mid and mid not in found:
                    found.append(mid)
        return found

    def _detect_time_horizon(self, q: str) -> Optional[str]:
        m = re.search(r"\b(next|last|past)\s+(\d+)\s+(years?|months?|quarters?)\b", q)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)}"
        m = re.search(r"\b(19|20)\d{2}\s*[-–to]+\s*(19|20)\d{2}\b", q)
        if m:
            return m.group(0)
        if re.search(r"\bafter\s+(19|20)\d{2}\b", q):
            return re.search(r"\bafter\s+(19|20)\d{2}\b", q).group(0)  # type: ignore
        return None

    def _pick_primary_metric(
        self,
        metrics: list[str],
        q: str,
        context: Optional[dict[str, Any]],
    ) -> tuple[str, str]:
        if metrics:
            # Prefer metric mentioned first in the question
            first = None
            first_pos = 10**9
            for mid, label, aliases in METRIC_CATALOG:
                if mid not in metrics:
                    continue
                for alias in aliases:
                    pos = q.find(alias)
                    if pos >= 0 and pos < first_pos:
                        first_pos = pos
                        first = mid
            mid = first or metrics[0]
            return mid, self._label_for(mid)

        # Infer from slowdown/growth language
        if re.search(r"\b(economy|economic|growth|slowed|slowdown|recession)\b", q):
            return "gdp", "GDP"
        if re.search(r"\b(prices? rising|price rise|cost of living)\b", q):
            return "inflation", "Inflation"
        if re.search(r"\b(jobs?|labor market|labour market)\b", q):
            return "unemployment", "Unemployment"
        if context and (context.get("metrics") or context.get("last_forecast_target")):
            label = (
                (context.get("metrics") or [None])[0]
                or context.get("last_forecast_target")
            )
            mid = self._metric_id_from_label(str(label)) or "gdp"
            return mid, self._label_for(mid)
        return "gdp", "GDP"  # safe default for macro-style research questions

    # ------------------------------------------------------------------
    # Dataset construction
    # ------------------------------------------------------------------

    def _build_datasets(
        self,
        *,
        objective_type: ResearchObjectiveType,
        primary_id: str,
        primary_label: str,
        secondary_ids: list[str],
        entities: list[str],
        question: str,
        max_datasets: int,
        notes: list[str],
    ) -> list[DatasetRequirement]:
        datasets: list[DatasetRequirement] = []
        primary_topic = self._topic_for(primary_id, entities)

        datasets.append(
            DatasetRequirement(
                topic=primary_topic,
                reason=f"Primary subject of the research question ({primary_label}).",
                priority=DatasetPriority.CRITICAL,
                necessity=DatasetNecessity.MANDATORY,
                role="primary_metric",
                entities=list(entities),
                order=1,
            )
        )

        # Comparison across entities: same metric for each entity
        if objective_type == ResearchObjectiveType.COMPARISON and len(entities) >= 2:
            for ent in entities[1:]:
                topic = f"{ent} {primary_label}"
                datasets.append(
                    DatasetRequirement(
                        topic=topic,
                        reason=f"Comparison counterpart for {entities[0] if entities else 'baseline'}.",
                        priority=DatasetPriority.CRITICAL,
                        necessity=DatasetNecessity.MANDATORY,
                        role="benchmark",
                        entities=[ent],
                        depends_on=[primary_topic],
                    )
                )
            notes.append("Multi-entity comparison: one series per entity.")

        # Benchmarking: primary + peer / world aggregates
        if objective_type == ResearchObjectiveType.BENCHMARKING:
            for mid in BENCHMARK_DEFAULTS:
                if mid == primary_id:
                    continue
                topic = self._topic_for(mid, entities)
                datasets.append(
                    DatasetRequirement(
                        topic=topic,
                        reason="Benchmarking companion indicator.",
                        priority=DatasetPriority.HIGH,
                        necessity=DatasetNecessity.OPTIONAL,
                        role="benchmark",
                        entities=list(entities),
                        depends_on=[primary_topic],
                    )
                )
            # Peer entity if only one country
            if len(entities) == 1:
                peer = "China" if entities[0] != "China" else "United States"
                datasets.append(
                    DatasetRequirement(
                        topic=f"{peer} {primary_label}",
                        reason=f"Peer benchmark for {entities[0]}.",
                        priority=DatasetPriority.HIGH,
                        necessity=DatasetNecessity.MANDATORY,
                        role="benchmark",
                        entities=[peer],
                        depends_on=[primary_topic],
                    )
                )

        # Root cause / impact expansions
        if objective_type in {
            ResearchObjectiveType.ROOT_CAUSE,
            ResearchObjectiveType.IMPACT,
        }:
            expansions = ROOT_CAUSE_EXPANSIONS.get(primary_id) or ROOT_CAUSE_EXPANSIONS.get(
                "gdp", []
            )
            if primary_id not in ROOT_CAUSE_EXPANSIONS:
                notes.append(
                    f"No domain expansion for '{primary_id}'; using GDP-style drivers as soft template."
                )
                expansions = [
                    e for e in ROOT_CAUSE_EXPANSIONS["gdp"]
                    if e[0] != primary_id
                ][:5]
            for mid, role, necessity, priority, reason in expansions:
                topic = self._topic_for(mid, entities)
                if any(d.topic.lower() == topic.lower() for d in datasets):
                    continue
                datasets.append(
                    DatasetRequirement(
                        topic=topic,
                        reason=reason,
                        priority=priority,
                        necessity=necessity,
                        role=role,
                        entities=list(entities),
                        depends_on=[primary_topic],
                    )
                )

        # Correlation: need at least two metrics
        if objective_type == ResearchObjectiveType.CORRELATION:
            for mid in secondary_ids or self._default_correlation_pair(primary_id):
                if mid == primary_id:
                    continue
                topic = self._topic_for(mid, entities)
                if any(d.topic.lower() == topic.lower() for d in datasets):
                    continue
                datasets.append(
                    DatasetRequirement(
                        topic=topic,
                        reason="Paired metric for correlation / relationship analysis.",
                        priority=DatasetPriority.HIGH,
                        necessity=DatasetNecessity.MANDATORY,
                        role="secondary_metric",
                        entities=list(entities),
                        depends_on=[primary_topic],
                    )
                )

        # Forecasting / trend: primary is enough; optional drivers for richer forecast
        if objective_type == ResearchObjectiveType.FORECASTING:
            for mid, role, _n, priority, reason in (
                ROOT_CAUSE_EXPANSIONS.get(primary_id) or []
            )[:3]:
                topic = self._topic_for(mid, entities)
                if any(d.topic.lower() == topic.lower() for d in datasets):
                    continue
                datasets.append(
                    DatasetRequirement(
                        topic=topic,
                        reason=f"Optional exogenous series for richer forecast. {reason}",
                        priority=DatasetPriority.LOW,
                        necessity=DatasetNecessity.OPTIONAL,
                        role=role,
                        entities=list(entities),
                        depends_on=[primary_topic],
                    )
                )

        if objective_type == ResearchObjectiveType.TREND:
            # Usually single primary; optional related if "drivers" language absent
            pass

        if objective_type == ResearchObjectiveType.MULTI_METRIC:
            for mid in secondary_ids:
                topic = self._topic_for(mid, entities)
                if any(d.topic.lower() == topic.lower() for d in datasets):
                    continue
                datasets.append(
                    DatasetRequirement(
                        topic=topic,
                        reason="User-requested multi-metric analysis.",
                        priority=DatasetPriority.HIGH,
                        necessity=DatasetNecessity.MANDATORY,
                        role="secondary_metric",
                        entities=list(entities),
                    )
                )

        if objective_type == ResearchObjectiveType.EXPLORATION and not secondary_ids:
            # Keep primary only unless macro "economy" implies multi
            if re.search(r"\b(economy|macro|economic health|overall)\b", question.lower()):
                for mid in ("inflation", "unemployment", "exports"):
                    topic = self._topic_for(mid, entities)
                    datasets.append(
                        DatasetRequirement(
                            topic=topic,
                            reason="Macro exploration companion.",
                            priority=DatasetPriority.MEDIUM,
                            necessity=DatasetNecessity.OPTIONAL,
                            role="context",
                            entities=list(entities),
                            depends_on=[primary_topic],
                        )
                    )

        return datasets

    def _default_correlation_pair(self, primary_id: str) -> list[str]:
        defaults = {
            "gdp": ["inflation"],
            "inflation": ["interest_rates"],
            "rainfall": ["crop_yield"],
            "crop_yield": ["rainfall"],
            "unemployment": ["gdp"],
            "exports": ["exchange_rate"],
        }
        return defaults.get(primary_id, ["gdp"] if primary_id != "gdp" else ["inflation"])

    def _order_and_cap(
        self, datasets: list[DatasetRequirement], max_datasets: int
    ) -> list[DatasetRequirement]:
        priority_rank = {
            DatasetPriority.CRITICAL: 0,
            DatasetPriority.HIGH: 1,
            DatasetPriority.MEDIUM: 2,
            DatasetPriority.LOW: 3,
        }
        necessity_rank = {
            DatasetNecessity.MANDATORY: 0,
            DatasetNecessity.OPTIONAL: 1,
        }
        # Dedupe by topic
        seen: set[str] = set()
        unique: list[DatasetRequirement] = []
        for d in datasets:
            key = d.topic.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(d)

        unique.sort(
            key=lambda d: (
                necessity_rank.get(d.necessity, 9),
                priority_rank.get(d.priority, 9),
                d.order or 99,
                d.topic,
            )
        )
        # Always keep all mandatory first, then fill optionals up to max
        mandatory = [d for d in unique if d.necessity == DatasetNecessity.MANDATORY]
        optional = [d for d in unique if d.necessity == DatasetNecessity.OPTIONAL]
        capped = mandatory[:max_datasets]
        room = max_datasets - len(capped)
        if room > 0:
            capped.extend(optional[:room])
        for i, d in enumerate(capped):
            d.order = i + 1
        return capped

    def _build_dependency_edges(
        self, datasets: list[DatasetRequirement]
    ) -> list[dict[str, str]]:
        edges: list[dict[str, str]] = []
        topics = {d.topic for d in datasets}
        for d in datasets:
            for dep in d.depends_on:
                if dep in topics and dep != d.topic:
                    edges.append({"from": dep, "to": d.topic})
        return edges

    def _build_analysis_goals(
        self,
        objective: ResearchObjective,
        datasets: list[DatasetRequirement],
        entities: list[str],
    ) -> list[AnalysisGoal]:
        topics = [d.topic for d in datasets]
        primary = topics[0] if topics else objective.primary_metric
        ot = objective.objective_type
        goals: list[AnalysisGoal] = []

        if ot == ResearchObjectiveType.ROOT_CAUSE:
            goals.append(
                AnalysisGoal(
                    goal_id="g_trend_primary",
                    description=f"Characterize the trend and slowdown periods in {primary}.",
                    goal_type="trend",
                    target_datasets=[primary],
                    priority=10,
                )
            )
            drivers = [d.topic for d in datasets if d.role == "driver"]
            if drivers:
                goals.append(
                    AnalysisGoal(
                        goal_id="g_correlate_drivers",
                        description=f"Correlate {primary} with candidate drivers.",
                        goal_type="correlation",
                        target_datasets=[primary] + drivers[:4],
                        priority=20,
                    )
                )
            goals.append(
                AnalysisGoal(
                    goal_id="g_root_cause_synthesis",
                    description="Synthesize which factors best explain the observed change.",
                    goal_type="root_cause",
                    target_datasets=topics[:6],
                    priority=30,
                )
            )
        elif ot == ResearchObjectiveType.COMPARISON:
            goals.append(
                AnalysisGoal(
                    goal_id="g_compare",
                    description=f"Compare {objective.primary_metric} across entities/metrics.",
                    goal_type="comparison",
                    target_datasets=topics,
                    priority=10,
                )
            )
        elif ot == ResearchObjectiveType.BENCHMARKING:
            goals.append(
                AnalysisGoal(
                    goal_id="g_benchmark",
                    description=f"Benchmark {primary} against peers and related indicators.",
                    goal_type="benchmarking",
                    target_datasets=topics,
                    priority=10,
                )
            )
        elif ot == ResearchObjectiveType.CORRELATION:
            goals.append(
                AnalysisGoal(
                    goal_id="g_correlation",
                    description="Quantify relationship strength between selected series.",
                    goal_type="correlation",
                    target_datasets=topics[:4],
                    priority=10,
                )
            )
        elif ot == ResearchObjectiveType.FORECASTING:
            goals.append(
                AnalysisGoal(
                    goal_id="g_forecast",
                    description=f"Forecast {primary}"
                    + (f" for {objective.time_horizon}" if objective.time_horizon else "")
                    + ".",
                    goal_type="forecast",
                    target_datasets=[primary],
                    priority=10,
                )
            )
            if len(topics) > 1:
                goals.append(
                    AnalysisGoal(
                        goal_id="g_exogenous",
                        description="Optionally condition forecast on related drivers.",
                        goal_type="forecast",
                        target_datasets=topics[:4],
                        priority=20,
                    )
                )
        elif ot == ResearchObjectiveType.TREND:
            goals.append(
                AnalysisGoal(
                    goal_id="g_trend",
                    description=f"Analyze historical trend of {primary}.",
                    goal_type="trend",
                    target_datasets=[primary],
                    priority=10,
                )
            )
        elif ot == ResearchObjectiveType.IMPACT:
            goals.append(
                AnalysisGoal(
                    goal_id="g_impact",
                    description=f"Estimate impact pathways related to {primary}.",
                    goal_type="impact",
                    target_datasets=topics[:5],
                    priority=10,
                )
            )
        else:
            goals.append(
                AnalysisGoal(
                    goal_id="g_explore",
                    description=f"Exploratory analysis of {primary} and related series.",
                    goal_type="exploration",
                    target_datasets=topics[:4],
                    priority=10,
                )
            )

        if entities:
            goals.append(
                AnalysisGoal(
                    goal_id="g_entity_focus",
                    description=f"Focus interpretation on {', '.join(entities)}.",
                    goal_type="context",
                    target_datasets=[primary],
                    priority=50,
                )
            )
        return goals

    def _build_expected_outputs(
        self,
        objective: ResearchObjective,
        goals: list[AnalysisGoal],
    ) -> list[ExpectedOutput]:
        ot = objective.objective_type
        outputs: list[ExpectedOutput] = [
            ExpectedOutput(
                output_type="insight",
                description="Narrative answer to the research question with supporting evidence.",
                related_goals=[g.goal_id for g in goals[:3]],
            )
        ]
        if ot in {
            ResearchObjectiveType.TREND,
            ResearchObjectiveType.ROOT_CAUSE,
            ResearchObjectiveType.FORECASTING,
            ResearchObjectiveType.COMPARISON,
            ResearchObjectiveType.BENCHMARKING,
        }:
            outputs.append(
                ExpectedOutput(
                    output_type="chart",
                    description="Time-series / comparison chart of primary and key related metrics.",
                    related_goals=[g.goal_id for g in goals if g.goal_type in {
                        "trend", "comparison", "forecast", "benchmarking", "root_cause",
                    }][:3],
                )
            )
        if ot in {ResearchObjectiveType.CORRELATION, ResearchObjectiveType.ROOT_CAUSE}:
            outputs.append(
                ExpectedOutput(
                    output_type="chart",
                    description="Correlation / scatter views between primary metric and drivers.",
                    related_goals=["g_correlate_drivers", "g_correlation"],
                )
            )
        if ot == ResearchObjectiveType.FORECASTING:
            outputs.append(
                ExpectedOutput(
                    output_type="forecast",
                    description="Forward projections with uncertainty band if available.",
                    related_goals=["g_forecast"],
                )
            )
        if ot in {
            ResearchObjectiveType.COMPARISON,
            ResearchObjectiveType.BENCHMARKING,
            ResearchObjectiveType.ROOT_CAUSE,
        }:
            outputs.append(
                ExpectedOutput(
                    output_type="comparison_table",
                    description="Tabular summary of key indicators / entities.",
                    related_goals=[g.goal_id for g in goals[:2]],
                )
            )
        outputs.append(
            ExpectedOutput(
                output_type="report_section",
                description="Structured research findings section for the copilot answer.",
                related_goals=[g.goal_id for g in goals],
            )
        )
        return outputs

    def _confidence(
        self,
        objective: ResearchObjective,
        datasets: list[DatasetRequirement],
        metrics: list[str],
    ) -> float:
        if not datasets:
            return 0.0
        score = 0.4
        if objective.primary_metric:
            score += 0.15
        if metrics:
            score += 0.1
        if objective.entities:
            score += 0.1
        if objective.objective_type != ResearchObjectiveType.EXPLORATION:
            score += 0.1
        if any(d.necessity == DatasetNecessity.MANDATORY for d in datasets):
            score += 0.1
        if len(datasets) >= 3 and objective.objective_type == ResearchObjectiveType.ROOT_CAUSE:
            score += 0.1
        return round(min(1.0, score), 4)

    def _objective_summary(
        self,
        ot: ResearchObjectiveType,
        primary: str,
        entities: list[str],
        question: str,
    ) -> str:
        ent = ", ".join(entities) if entities else "the subject"
        mapping = {
            ResearchObjectiveType.ROOT_CAUSE: f"Identify drivers behind changes in {primary} for {ent}.",
            ResearchObjectiveType.COMPARISON: f"Compare {primary} across entities or series for {ent}.",
            ResearchObjectiveType.BENCHMARKING: f"Benchmark {primary} for {ent} against peers/indicators.",
            ResearchObjectiveType.CORRELATION: f"Measure relationships involving {primary} for {ent}.",
            ResearchObjectiveType.FORECASTING: f"Forecast {primary} for {ent}.",
            ResearchObjectiveType.TREND: f"Analyze the trend of {primary} for {ent}.",
            ResearchObjectiveType.IMPACT: f"Assess impacts related to {primary} for {ent}.",
            ResearchObjectiveType.MULTI_METRIC: f"Joint multi-metric analysis including {primary}.",
            ResearchObjectiveType.EXPLORATION: f"Explore {primary} and related context for {ent}.",
        }
        return mapping.get(ot, question[:160])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _label_for(self, metric_id: str) -> str:
        for mid, label, _ in METRIC_CATALOG:
            if mid == metric_id:
                return label
        # Unknown ids like food_prices
        return metric_id.replace("_", " ").title()

    def _metric_id_from_label(self, text: str) -> Optional[str]:
        t = (text or "").lower()
        for mid, label, aliases in METRIC_CATALOG:
            if mid in t or label.lower() in t:
                return mid
            for a in aliases:
                if a in t:
                    return mid
        return None

    def _topic_for(self, metric_id: str, entities: list[str]) -> str:
        label = self._label_for(metric_id)
        if entities:
            # Primary entity prefixes topic for country-specific research
            return f"{entities[0]} {label}"
        return label
