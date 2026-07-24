"""100 end-to-end evaluation test cases across 10 categories."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class EvalTestCase:
    """One evaluation scenario."""

    id: int
    category: str
    question: str
    # Optional multi-turn sequence (follow-ups). First item is opening question.
    conversation: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    # Soft expectations used by scoring (not hard unit asserts)
    expect_intent: Optional[str] = None  # analysis|comparison|correlation|forecast|discovery|explain|edge|stress
    expect_multi_dataset: bool = False
    expect_tools: list[str] = field(default_factory=list)
    expect_metrics: list[str] = field(default_factory=list)
    expect_entities: list[str] = field(default_factory=list)
    expect_graceful_failure: bool = False
    expect_explanation: bool = False
    timeout_seconds: float = 120.0
    notes: str = ""

    def primary_question(self) -> str:
        if self.conversation:
            return self.conversation[0]
        return self.question

    def turns(self) -> list[str]:
        if self.conversation:
            return list(self.conversation)
        return [self.question]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def all_test_cases() -> list[EvalTestCase]:
    """Return the full 100-case suite in stable order."""
    cases: list[EvalTestCase] = []
    cases.extend(_category_1_single())
    cases.extend(_category_2_comparison())
    cases.extend(_category_3_correlation())
    cases.extend(_category_4_forecasting())
    cases.extend(_category_5_multi())
    cases.extend(_category_6_followup())
    cases.extend(_category_7_discovery())
    cases.extend(_category_8_explainability())
    cases.extend(_category_9_edge())
    cases.extend(_category_10_stress())
    assert len(cases) == 100, f"Expected 100 cases, got {len(cases)}"
    return cases


def cases_by_category(category: str | None = None) -> list[EvalTestCase]:
    cases = all_test_cases()
    if not category:
        return cases
    key = category.strip().lower()
    return [c for c in cases if c.category.lower() == key or key in c.category.lower()]


def cases_by_ids(ids: list[int]) -> list[EvalTestCase]:
    wanted = set(ids)
    return [c for c in all_test_cases() if c.id in wanted]


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def _category_1_single() -> list[EvalTestCase]:
    cat = "1_single_dataset"
    items = [
        (1, "Analyze India's GDP from 2000–2024.", ["gdp", "india"], ["GDP"], ["India"]),
        (2, "Show India's population trend.", ["population", "trend"], ["Population"], ["India"]),
        (3, "Visualize Seattle weather.", ["weather", "viz"], [], ["Seattle"]),
        (4, "Forecast gold prices.", ["gold", "forecast"], ["Gold Price"], []),
        (5, "Analyze rainfall in India.", ["rainfall"], ["Rainfall"], ["India"]),
        (6, "Show unemployment trend in India.", ["unemployment", "trend"], ["Unemployment"], ["India"]),
        (7, "Analyze COVID cases by month.", ["covid"], [], []),
        (8, "Visualize crude oil prices.", ["oil", "viz"], ["Oil Price"], []),
        (9, "Analyze Bitcoin prices.", ["bitcoin"], [], []),
        (10, "Show inflation trend.", ["inflation", "trend"], ["Inflation"], []),
    ]
    out = []
    for i, q, tags, metrics, entities in items:
        intent = "forecast" if "forecast" in q.lower() else "analysis"
        out.append(
            EvalTestCase(
                id=i,
                category=cat,
                question=q,
                tags=tags,
                expect_intent=intent,
                expect_metrics=metrics,
                expect_entities=entities,
                expect_tools=["forecast"] if intent == "forecast" else [],
            )
        )
    return out


def _category_2_comparison() -> list[EvalTestCase]:
    cat = "2_comparison"
    items = [
        (11, "Compare India and China GDP.", ["gdp"], ["GDP"], ["India", "China"]),
        (12, "Compare India and USA population.", ["population"], ["Population"], ["India", "United States"]),
        (13, "Compare inflation of India and Brazil.", ["inflation"], ["Inflation"], ["India", "Brazil"]),
        (14, "Compare rainfall of Delhi and Mumbai.", ["rainfall"], ["Rainfall"], []),
        (15, "Compare GDP before and after COVID.", ["gdp", "covid"], ["GDP"], []),
        (16, "Compare male and female literacy.", ["literacy"], [], []),
        (17, "Compare CO₂ emissions of G20 countries.", ["co2"], ["CO2 Emissions"], []),
        (18, "Compare gold and silver prices.", ["gold", "silver"], ["Gold Price"], []),
        (19, "Compare rainfall and crop production.", ["rainfall", "crop"], ["Rainfall", "Crop Yield"], []),
        (20, "Compare EV sales in India and China.", ["ev"], [], ["India", "China"]),
    ]
    return [
        EvalTestCase(
            id=i,
            category=cat,
            question=q,
            tags=tags,
            expect_intent="comparison",
            expect_multi_dataset=True,
            expect_metrics=metrics,
            expect_entities=entities,
            expect_tools=["comparison"],
        )
        for i, q, tags, metrics, entities in items
    ]


def _category_3_correlation() -> list[EvalTestCase]:
    cat = "3_correlation"
    items = [
        (21, "Relationship between rainfall and crop yield.", ["rainfall", "crop"], ["Rainfall", "Crop Yield"]),
        (22, "GDP vs Inflation.", ["gdp", "inflation"], ["GDP", "Inflation"]),
        (23, "Population vs CO₂ emissions.", ["population", "co2"], ["Population", "CO2 Emissions"]),
        (24, "GDP vs Electricity consumption.", ["gdp", "electricity"], ["GDP", "Energy"]),
        (25, "Temperature vs electricity demand.", ["temperature", "electricity"], ["Temperature", "Energy"]),
        (26, "Income vs life expectancy.", ["income"], []),
        (27, "Rainfall vs reservoir level.", ["rainfall"], ["Rainfall"]),
        (28, "Gold price vs USD.", ["gold", "usd"], ["Gold Price", "Exchange Rate"]),
        (29, "Oil price vs inflation.", ["oil", "inflation"], ["Oil Price", "Inflation"]),
        (30, "GDP vs unemployment.", ["gdp", "unemployment"], ["GDP", "Unemployment"]),
    ]
    return [
        EvalTestCase(
            id=i,
            category=cat,
            question=q,
            tags=tags,
            expect_intent="correlation",
            expect_multi_dataset=True,
            expect_metrics=metrics,
            expect_tools=["correlation", "scatter_plot"],
        )
        for i, q, tags, metrics in items
    ]


def _category_4_forecasting() -> list[EvalTestCase]:
    cat = "4_forecasting"
    items = [
        (31, "Forecast India's GDP.", ["gdp"], ["GDP"], ["India"]),
        (32, "Forecast inflation.", ["inflation"], ["Inflation"], []),
        (33, "Forecast gold prices.", ["gold"], ["Gold Price"], []),
        (34, "Forecast rainfall.", ["rainfall"], ["Rainfall"], []),
        (35, "Forecast unemployment.", ["unemployment"], ["Unemployment"], []),
        (36, "Forecast Bitcoin.", ["bitcoin"], [], []),
        (37, "Forecast EV sales.", ["ev"], [], []),
        (38, "Forecast population.", ["population"], ["Population"], []),
        (39, "Forecast electricity demand.", ["electricity"], ["Energy"], []),
        (40, "Forecast tourism.", ["tourism"], [], []),
    ]
    return [
        EvalTestCase(
            id=i,
            category=cat,
            question=q,
            tags=tags + ["forecast"],
            expect_intent="forecast",
            expect_metrics=metrics,
            expect_entities=entities,
            expect_tools=["forecast", "trend"],
        )
        for i, q, tags, metrics, entities in items
    ]


def _category_5_multi() -> list[EvalTestCase]:
    cat = "5_multi_dataset"
    items = [
        (41, "Compare GDP, Inflation and Population.", ["GDP", "Inflation", "Population"]),
        (42, "Compare GDP, Inflation, CO₂.", ["GDP", "Inflation", "CO2 Emissions"]),
        (43, "Compare rainfall, crop production and temperature.", ["Rainfall", "Crop Yield", "Temperature"]),
        (44, "Compare gold, silver and USD.", ["Gold Price", "Exchange Rate"]),
        (45, "Compare exports, imports and GDP.", ["Exports", "Imports", "GDP"]),
        (46, "Analyze renewable energy adoption.", ["Energy"]),
        (47, "Compare electricity demand and weather.", ["Energy", "Temperature"]),
        (48, "Compare oil price and inflation.", ["Oil Price", "Inflation"]),
        (49, "Compare population, literacy and income.", ["Population"]),
        (50, "Compare GDP, unemployment and inflation.", ["GDP", "Unemployment", "Inflation"]),
    ]
    return [
        EvalTestCase(
            id=i,
            category=cat,
            question=q,
            tags=["multi"],
            expect_intent="comparison",
            expect_multi_dataset=True,
            expect_metrics=metrics,
        )
        for i, q, metrics in items
    ]


def _category_6_followup() -> list[EvalTestCase]:
    cat = "6_followup"
    # Single multi-turn scenario spanning cases 51–60 as sequential conversation eval
    # Each case is also runnable as a step with conversation prefix for isolation.
    base = [
        "Analyze India's GDP.",
        "Now compare it with China.",
        "Only after 2010.",
        "Forecast next five years.",
        "Show logarithmic scale.",
        "Export report.",
        "Use previous dataset.",
        "Only show southern states.",
        "Compare with previous analysis.",
        "Reset conversation.",
    ]
    out: list[EvalTestCase] = []
    for idx, turn in enumerate(base):
        case_id = 51 + idx
        out.append(
            EvalTestCase(
                id=case_id,
                category=cat,
                question=turn,
                conversation=base[: idx + 1],
                tags=["followup", "context"],
                expect_intent="analysis" if idx == 0 else "followup",
                expect_entities=["India"] if idx < 9 else [],
                notes="Follow-up conversation turn",
            )
        )
    return out


def _category_7_discovery() -> list[EvalTestCase]:
    cat = "7_discovery"
    items = [
        (61, "Find a dataset about EV sales."),
        (62, "Find healthcare expenditure dataset."),
        (63, "Find renewable energy dataset."),
        (64, "Find world happiness dataset."),
        (65, "Find crime statistics."),
        (66, "Find rainfall dataset."),
        (67, "Find tourism dataset."),
        (68, "Find education dataset."),
        (69, "Find CO₂ dataset."),
        (70, "Find air pollution dataset."),
    ]
    return [
        EvalTestCase(
            id=i,
            category=cat,
            question=q,
            tags=["discovery", "search"],
            expect_intent="discovery",
        )
        for i, q in items
    ]


def _category_8_explainability() -> list[EvalTestCase]:
    cat = "8_explainability"
    items = [
        (71, "Why did you choose this dataset?", "dataset_choice"),
        (72, "Show reasoning.", "reasoning"),
        (73, "Explain joins.", "joins"),
        (74, "Explain confidence.", "confidence"),
        (75, "Show limitations.", "limitations"),
        (76, "Show filters.", "filters"),
        (77, "Show columns used.", "columns"),
        (78, "Show analytical tools.", "tools"),
        (79, "Show citations.", "citations"),
        (80, "Give technical explanation.", "technical"),
    ]
    return [
        EvalTestCase(
            id=i,
            category=cat,
            question=q,
            tags=["explain", tag],
            expect_intent="explain",
            expect_explanation=True,
            # Seed conversation so explainer has prior analysis context
            conversation=["Analyze India's GDP.", q],
        )
        for i, q, tag in items
    ]


def _category_9_edge() -> list[EvalTestCase]:
    cat = "9_edge_cases"
    items = [
        (81, "Analyze GDP on Mars.", True),
        (82, "Compare GDP with rainfall on Jupiter.", True),
        (83, "Analyze empty dataset.", True),
        (84, "Forecast using one data point.", True),
        (85, "Join incompatible datasets.", True),
        (86, "Dataset not found.", True),
        (87, "Corrupted CSV.", True),
        (88, "Network timeout.", True),
        (89, "Duplicate datasets.", False),
        (90, "Very large dataset (>1 GB).", True),
    ]
    return [
        EvalTestCase(
            id=i,
            category=cat,
            question=q,
            tags=["edge"],
            expect_intent="edge",
            expect_graceful_failure=graceful,
            notes="Edge / failure-recovery scenario",
        )
        for i, q, graceful in items
    ]


def _category_10_stress() -> list[EvalTestCase]:
    cat = "10_stress"
    long_prompt = (
        "Please perform a comprehensive multi-factor macroeconomic analysis "
        "covering historical trends, structural breaks, external shocks, "
        "policy regimes, and forecasting uncertainty. " * 20
    )
    items = [
        (91, "Run 20 analyses simultaneously.", ["stress", "concurrency"]),
        (92, "Retrieve same dataset 10 times.", ["stress", "cache"]),
        (93, long_prompt.strip(), ["stress", "long_prompt"]),
        (94, "Analyze a 100-column dataset.", ["stress", "wide"]),
        (95, "Analyze a 1 million row dataset.", ["stress", "large"]),
        (96, "Rapid follow-up questions.", ["stress", "followup"]),
        (97, "Multiple users.", ["stress", "multi_user"]),
        (98, "Repeated semantic searches.", ["stress", "semantic"]),
        (99, "Repeated report generation.", ["stress", "report"]),
        (100, "Long conversation (100 turns).", ["stress", "long_conversation"]),
    ]
    out = []
    for i, q, tags in items:
        conv: list[str] = []
        if i == 96:
            conv = [
                "Analyze India's GDP.",
                "Compare with China.",
                "After 2010.",
                "Forecast 5 years.",
                "Show chart.",
            ]
        elif i == 100:
            conv = [f"Follow-up turn {n} about India GDP analysis." for n in range(1, 21)]
            conv[0] = "Analyze India's GDP."
        out.append(
            EvalTestCase(
                id=i,
                category=cat,
                question=q if not conv else conv[-1],
                conversation=conv,
                tags=tags,
                expect_intent="stress",
                timeout_seconds=180.0 if i in {91, 95, 100} else 120.0,
                notes="Stress / load scenario — bounded synthetic execution",
            )
        )
    return out
