import json

from backend.config import settings
from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm
from backend.utils.intent_classifier import classify_intents

logger = get_logger(__name__)

VALID_PLANNER_NODES = {
    "load_data",
    "fetch_data",
    "profile_data",
    "recommend_analysis",
    "dataset_topic_detection",
    "dataset_topic_agent",
    "dataset_search_agent",
    "pattern_detection",
    "explain_dataset",
    "clean_data",
    "run_eda",
    "run_viz",
    "run_multi_viz",
    "run_qa",
    "forecast_data",
    "chart_interpretation",
    "hypothesis_generation",
    "dataset_embedding_search",
    "compare_datasets",
    "generate_insight",
}

DATASET_KEYWORDS = [
    "gdp",
    "population",
    "inflation",
    "climate",
    "temperature",
    "sales",
    "revenue",
    "stock",
    "unemployment",
    "energy",
    "covid",
    "electric vehicle",
    "co2",
]


def _dedupe_plan(plan):
    validated_plan = _validate_plan(plan)
    deduped = []
    for step in validated_plan:
        if step not in deduped:
            deduped.append(step)

    if not deduped and plan:
        logger.warning(
            "Planner fallback to generate_insight",
            extra={"original_plan": plan},
        )
        deduped = ["generate_insight"]

    return deduped


def _validate_plan(plan):
    validated = [step for step in plan if step in VALID_PLANNER_NODES]
    invalid = [step for step in plan if step not in VALID_PLANNER_NODES]
    if invalid:
        logger.warning(
            "Planner removed invalid plan nodes",
            extra={"invalid_nodes": invalid, "plan": plan},
        )
    return validated


def _detect_chart_type(question: str) -> str:
    if "heatmap" in question or "correlation" in question:
        return "heatmap"
    if "scatter" in question or "vs" in question:
        return "scatter"
    if "line" in question or "trend" in question:
        return "line"
    if "box" in question or "category" in question:
        return "box"
    return "visualization"


def _extract_json(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


def _parse_planner_response(response: str) -> list[str]:
    if not response:
        return []

    try:
        payload = json.loads(response)
    except Exception:
        payload = _extract_json(response)
        if payload:
            try:
                payload = json.loads(payload)
            except Exception:
                return []
        else:
            return []

    if not isinstance(payload, dict):
        return []

    plan = payload.get("plan")
    if not isinstance(plan, list):
        return []

    return [str(step).strip() for step in plan if isinstance(step, str) and step.strip()]


def _normalize_plan_steps(plan):
    mapping = {
        "dataset_topic_detection": "dataset_topic_agent",
        "dataset_search": "dataset_search_agent",
    }
    return [mapping.get(step, step) for step in plan]


def _build_llm_plan(question: str, dataset_available: bool) -> list[str]:
    prompt = f"""
You are an analytics workflow planner for an AI Data Analyst.

Available steps:
- dataset_topic_agent
- dataset_search_agent
- fetch_data
- clean_data
- profile_data
- run_eda
- pattern_detection
- run_viz
- chart_interpretation
- hypothesis_generation
- recommend_analysis
- run_qa
- forecast_data
- compare_datasets
- generate_insight

User Question:
{question}

Dataset Available:
{"yes" if dataset_available else "no"}

Return ONLY JSON:
{{
  "plan": [...]
}}

Rules:
- If no dataset is available, start with dataset_topic_agent -> dataset_search_agent -> fetch_data.
- Always prepare data: clean_data then profile_data before analysis.
- Full analysis should include run_eda, run_viz, recommend_analysis, generate_insight.
- Use forecast_data for prediction requests.
- Use compare_datasets for comparison requests.
- End with generate_insight.
"""

    logger.info("LLM PLANNER INVOKED", extra={"question": question, "model": settings.OLLAMA_MODEL})
    response = invoke_llm(prompt)
    return _normalize_plan_steps(_parse_planner_response(response))


def _infer_operation(plan: list[str]) -> str | None:
    if "forecast_data" in plan:
        return "forecast"
    if "compare_datasets" in plan:
        return "comparison"
    if "run_viz" in plan:
        return "visualization"
    if "run_qa" in plan:
        return "statistical_analysis"
    if "run_eda" in plan:
        return "analyze"
    return None


def _discovery_prefix(state, force: bool = False) -> list[str]:
    """Steps to discover and load data when nothing is active."""
    if state.get("data") is not None and not force:
        return []
    if state.get("file_path"):
        return ["load_data"]
    return [
        "dataset_topic_agent",
        "dataset_search_agent",
        "fetch_data",
    ]


def _analysis_suffix(include_viz: bool = True) -> list[str]:
    steps = [
        "clean_data",
        "profile_data",
        "run_eda",
        "pattern_detection",
    ]
    if include_viz:
        steps.extend(["run_viz", "chart_interpretation"])
    steps.extend(
        [
            "hypothesis_generation",
            "recommend_analysis",
            "generate_insight",
        ]
    )
    return steps


def _build_rule_based_plan(state, normalized, intents, dataset_requested):
    has_data = state.get("data") is not None
    reuse = bool(state.get("reuse_active_dataset")) and has_data

    # --- Comparison (country or multi-metric) ---
    if "comparison" in intents:
        if not has_data and not dataset_requested:
            has_compare_signal = any(
                token in normalized
                for token in (
                    "gdp",
                    "population",
                    "inflation",
                    "compare",
                    "vs",
                    "versus",
                    "india",
                    "united states",
                    "usa",
                )
            )
            if not has_compare_signal:
                state["answer"] = (
                    "I could not determine which datasets or countries to compare. "
                    "Try: 'Compare GDP and Population' or 'Compare GDP of India with US'."
                )
                state["stop"] = True
                return []

        plan = _discovery_prefix(state)
        # Comparison agent can load its own sources; still profile when data exists.
        if has_data or plan:
            plan = plan + ["profile_data"]
        plan.extend(["compare_datasets", "recommend_analysis", "generate_insight"])
        return plan

    # --- Forecasting ---
    if "forecasting" in intents:
        if not has_data and not dataset_requested and not state.get("dataset_url"):
            state["answer"] = (
                "I could not determine which dataset to forecast. "
                "Try specifying one like GDP, population, or climate — "
                "or analyze a dataset first, then say 'forecast it'."
            )
            state["stop"] = True
            return []

        if reuse or has_data:
            return [
                "profile_data",
                "forecast_data",
                "chart_interpretation",
                "recommend_analysis",
                "generate_insight",
            ]

        return _discovery_prefix(state) + [
            "clean_data",
            "profile_data",
            "forecast_data",
            "chart_interpretation",
            "recommend_analysis",
            "generate_insight",
        ]

    # --- Explicit visualization ---
    if "visualization" in intents and "eda" not in intents and "dataset_autoload" not in intents:
        if reuse or has_data:
            return [
                "profile_data",
                "run_viz",
                "chart_interpretation",
                "recommend_analysis",
                "generate_insight",
            ]
        return _discovery_prefix(state) + [
            "clean_data",
            "profile_data",
            "run_viz",
            "chart_interpretation",
            "recommend_analysis",
            "generate_insight",
        ]

    # --- Statistical QA ---
    if "statistical_analysis" in intents and "eda" not in intents:
        if reuse or has_data:
            return ["profile_data", "run_qa", "recommend_analysis", "generate_insight"]
        return _discovery_prefix(state) + [
            "clean_data",
            "profile_data",
            "run_qa",
            "recommend_analysis",
            "generate_insight",
        ]

    # --- Full auto analysis (default ChatGPT-like path) ---
    # Covers: analyze X, dataset_autoload, eda, explanation, open-ended topics
    if reuse or (has_data and not dataset_requested):
        return ["profile_data"] + _analysis_suffix(include_viz=True)

    # Discovery + full analysis pipeline
    plan = _discovery_prefix(state) + _analysis_suffix(include_viz=True)

    # If user also asked for a chart explicitly, multi-viz is optional; run_viz is enough.
    if "visualization" in intents and "run_viz" not in plan:
        plan.insert(-2, "run_viz")

    return plan


def planner_agent(state):
    question = (state.get("question") or "").strip()
    normalized = question.lower()

    logger.info(
        "Planner received question",
        extra={
            "action": "plan",
            "question": question,
            "dataset": state.get("dataset_url") or state.get("file_path"),
            "has_data": state.get("data") is not None,
        },
    )

    # Reuse intents from conversation context when available to avoid duplicate work.
    intents = state.get("intents") or classify_intents(question)
    state["intents"] = intents
    state["last_intent"] = intents[0] if intents else None

    dataset_requested = any(keyword in normalized for keyword in DATASET_KEYWORDS)
    dataset_available = bool(
        state.get("data") is not None
        or state.get("dataset_url")
        or state.get("file_path")
    )

    # Product default: deterministic rule-based plan first (reliable + fast).
    plan = _build_rule_based_plan(state, normalized, intents, dataset_requested)

    # Opt-in LLM planner only when enabled and rules produced nothing usable.
    if (
        not plan
        and not state.get("stop")
        and bool(getattr(settings, "USE_LLM_PLANNER", False))
    ):
        plan = _build_llm_plan(question, dataset_available)

    # Ensure comparison is never dropped.
    comparison_requested = (
        "comparison" in intents
        or any(token in normalized for token in ("compare", " vs ", "versus"))
    )
    if comparison_requested and "compare_datasets" not in plan:
        if "generate_insight" in plan:
            plan.insert(plan.index("generate_insight"), "compare_datasets")
        else:
            plan.append("compare_datasets")

    # Ensure forecasting is never dropped when requested.
    if "forecasting" in intents and "forecast_data" not in plan and not state.get("stop"):
        if "generate_insight" in plan:
            plan.insert(plan.index("generate_insight"), "forecast_data")
        else:
            plan.append("forecast_data")

    if "dataset_search_agent" in plan and "dataset_topic_agent" not in plan:
        index = plan.index("dataset_search_agent")
        plan.insert(index, "dataset_topic_agent")

    # No data yet and no discovery/load steps — inject discovery.
    if (
        not dataset_available
        and "fetch_data" not in plan
        and "load_data" not in plan
        and "compare_datasets" not in plan
        and not state.get("stop")
    ):
        plan = [
            "dataset_topic_agent",
            "dataset_search_agent",
            "fetch_data",
        ] + [step for step in plan if step not in {
            "dataset_topic_agent",
            "dataset_search_agent",
            "fetch_data",
        }]

    # Active dataset reuse (follow-ups like "forecast it"): skip rediscovery.
    if state.get("data") is not None and state.get("reuse_active_dataset"):
        plan = [
            step
            for step in plan
            if step
            not in {
                "dataset_topic_agent",
                "dataset_topic_detection",
                "dataset_search_agent",
                "fetch_data",
            }
        ]
    elif state.get("data") is not None and not dataset_requested:
        # Same session, no new topic named — keep working on the active frame.
        plan = [step for step in plan if step not in {"fetch_data", "dataset_search_agent"}]
    elif state.get("data") is not None and dataset_requested and not state.get("reuse_active_dataset"):
        # User asked about a named topic while another frame is loaded — rediscover.
        # Data Engineer will replace state["data"] on successful fetch.
        if "fetch_data" not in plan:
            insert_at = 0
            for marker in ("dataset_search_agent", "dataset_topic_agent", "load_data"):
                if marker in plan:
                    insert_at = plan.index(marker) + 1
            plan.insert(insert_at, "fetch_data")
        # Force engineer to download even if a previous frame is present.
        state["force_reload_dataset"] = True

    if state.get("file_path") and state.get("data") is None and "load_data" not in plan:
        plan.insert(0, "load_data")

    # Always terminate with insights when analysis steps exist.
    if plan and "generate_insight" not in plan and not state.get("stop"):
        plan.append("generate_insight")

    plan = _dedupe_plan(plan)
    state["plan"] = plan

    logger.info(
        "Planner produced execution plan",
        extra={"action": "plan", "plan": plan, "intents": intents},
    )

    if not state.get("last_operation"):
        state["last_operation"] = _infer_operation(plan) or "workflow"

    if "run_viz" in plan:
        state["last_chart_type"] = _detect_chart_type(normalized)

    return state
