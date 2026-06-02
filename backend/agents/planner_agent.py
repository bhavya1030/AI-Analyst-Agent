import json

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


def _ensure_dataset_loaded(state, plan):
    if state.get("data") is not None:
        if "fetch_data" in plan:
            plan.remove("fetch_data")
        return True

    if state.get("file_path"):
        if "load_data" not in plan:
            plan.append("load_data")
        return True

    if "fetch_data" not in plan and "dataset_search_agent" not in plan:
        plan.insert(0, "dataset_search_agent")
    return False


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


def _has_time_series(profile):
    return bool(profile.get("time_columns") and profile.get("numeric_columns"))


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
You are an analytics workflow planner.

Available steps:
- fetch_data
- dataset_search_agent
- dataset_topic_agent
- profile_data
- run_eda
- run_viz
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
- Use fetch_data if dataset required.
- Use dataset_search_agent when no dataset is loaded and the user needs an external dataset.
- Use dataset_topic_agent before dataset_search_agent.
- Use profile_data before analysis.
- Use forecast_data for prediction requests.
- Use run_viz for visualization requests.
- Use compare_datasets for comparison requests.
- Use generate_insight to conclude the workflow.
"""

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


def _build_rule_based_plan(state, normalized, intents, dataset_requested):
    plan = []

    if "dataset_search" in intents or "dataset_autoload" in intents:
        plan.extend([
            "dataset_topic_agent",
            "dataset_search_agent",
            "fetch_data",
            "profile_data",
        ])
        if "visualization" in intents:
            plan.append("run_viz")
        if "statistical_analysis" in intents:
            plan.append("run_qa")
        if "explanation" in intents:
            plan.append("generate_insight")
        return plan

    if "forecasting" in intents:
        if not state.get("data") and not dataset_requested:
            state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
            state["stop"] = True
            return []

        return [
            "dataset_topic_agent",
            "dataset_search_agent",
            "fetch_data",
            "profile_data",
            "forecast_data",
            "chart_interpretation",
            "hypothesis_generation",
        ]

    if "comparison" in intents:
        if not state.get("data") and not dataset_requested:
            state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
            state["stop"] = True
            return []

        return [
            "dataset_topic_agent",
            "dataset_search_agent",
            "fetch_data",
            "profile_data",
            "compare_datasets",
            "generate_insight",
        ]

    if "visualization" in intents:
        return [
            "dataset_topic_agent",
            "dataset_search_agent",
            "fetch_data",
            "profile_data",
            "run_viz",
            "generate_insight",
        ]

    if "statistical_analysis" in intents or "explanation" in intents:
        return [
            "dataset_topic_agent",
            "dataset_search_agent",
            "fetch_data",
            "profile_data",
            "run_qa",
            "generate_insight",
        ]

    return [
        "dataset_topic_agent",
        "dataset_search_agent",
        "fetch_data",
        "profile_data",
        "run_eda",
        "generate_insight",
    ]


def planner_agent(state):
    question = (state.get("question") or "").strip()
    normalized = question.lower()

    logger.info(
        "Planner received question",
        extra={"action": "plan", "question": question, "dataset": state.get("dataset_url") or state.get("file_path")},
    )

    intents = classify_intents(question)
    state["last_intent"] = intents[0] if intents else None

    dataset_keywords = [
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
    ]
    dataset_requested = any(keyword in normalized for keyword in dataset_keywords)
    dataset_available = bool(state.get("data") or state.get("dataset_url") or state.get("file_path"))
    profile = state.get("dataset_profile") or {}

    plan = _build_llm_plan(question, dataset_available)
    if not plan:
        plan = _build_rule_based_plan(state, normalized, intents, dataset_requested)

    if "dataset_search_agent" in plan and "dataset_topic_agent" not in plan:
        index = plan.index("dataset_search_agent")
        plan.insert(index, "dataset_topic_agent")

    if not dataset_available and "dataset_search_agent" not in plan:
        plan.insert(0, "dataset_topic_agent")
        plan.insert(1, "dataset_search_agent")

    if dataset_available and "fetch_data" in plan:
        plan = [step for step in plan if step != "fetch_data"]

    plan = _dedupe_plan(plan)
    state["plan"] = plan

    if not state.get("last_operation"):
        state["last_operation"] = _infer_operation(plan) or "workflow"

    if "run_viz" in plan:
        state["last_chart_type"] = _detect_chart_type(normalized)

    return state

