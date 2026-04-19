from backend.core.logger import get_logger
from backend.utils.intent_classifier import classify_intents

logger = get_logger(__name__)

VALID_PLANNER_NODES = {
    "load_data",
    "fetch_data",
    "profile_data",
    "recommend_analysis",
    "dataset_topic_detection",
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
        # Remove fetch_data if dataset is already loaded
        if "fetch_data" in plan:
            plan.remove("fetch_data")
        return True

    if state.get("file_path"):
        if "load_data" not in plan:
            plan.append("load_data")
        return True

    # If no dataset, insert fetch_data at the beginning
    if "fetch_data" not in plan:
        plan.insert(0, "fetch_data")
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


def _has_correlation(profile):
    return len(profile.get("numeric_columns", [])) >= 2


def _has_category_analysis(profile):
    return bool(profile.get("categorical_columns") and profile.get("numeric_columns"))


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


def _plan_deep_analysis(state, profile, plan):
    plan.extend([
        "profile_data",
        "recommend_analysis",
        "dataset_topic_detection",
        "pattern_detection",
        "run_multi_viz",
        "chart_interpretation",
        "hypothesis_generation",
    ])

    if _has_time_series(profile):
        plan.append("forecast_data")

    state["last_operation"] = "deep_analysis"
    state["last_chart_type"] = "multi"


def planner_agent(state):
    question = (state.get("question") or "").strip()
    normalized = question.lower()

    logger.info(
        "Planner received question",
        extra={"action": "plan", "question": question, "dataset": state.get("dataset_url") or state.get("file_path")},
    )

    intents = classify_intents(normalized)

    logger.info(
        "Planner detected intents",
        extra={"action": "plan", "intents": intents},
    )

    # Dataset topic detection
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
        "covid"
    ]
    dataset_requested = any(keyword in normalized for keyword in dataset_keywords)

    profile = state.get("dataset_profile") or {}
    plan = []
    state["last_intent"] = intents[0] if intents else None
    state["last_operation"] = None

    if "dataset_search" in intents:
        plan.extend([
            "fetch_data",
            "profile_data",
            "dataset_topic_detection",
            "pattern_detection",
        ])

        if "similar" in normalized:
            plan.append("dataset_embedding_search")

        if "visualization" in intents:
            plan.append("run_viz")
            state["last_chart_type"] = _detect_chart_type(normalized)
            state["last_operation"] = "visualization"
        elif "statistical_analysis" in intents:
            plan.append("run_qa")
            state["last_operation"] = "statistical_analysis"
        elif "explanation" in intents:
            plan.append("explain_dataset")
            state["last_operation"] = "explain"
        else:
            plan.append("recommend_analysis")
            state["last_operation"] = "recommend"

        state["plan"] = _dedupe_plan(plan)
        return state

    if "dataset_autoload" in intents:
        plan.extend([
            "fetch_data",
            "profile_data"
        ])
        # Continue to other logic instead of returning early

    if "auto_analysis" in intents or "analyze dataset" in normalized or "analyze deeply" in normalized:
        dataset_available = _ensure_dataset_loaded(state, plan)
        
        if not dataset_available and not dataset_requested:
            state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
            state["stop"] = True
            return state
        
        if "deeply" in normalized or "deep analysis" in normalized or "analyze deeply" in normalized:
            _plan_deep_analysis(state, profile, plan)
        else:
            plan.extend([
                "profile_data",
                "recommend_analysis",
                "dataset_topic_detection",
                "pattern_detection",
                "run_eda",
                "run_viz",
                "chart_interpretation",
                "hypothesis_generation",
            ])
            if "forecast" in normalized or _has_time_series(profile):
                plan.append("forecast_data")
            state["last_operation"] = "analyze"
            state["last_chart_type"] = "multi"

        if "statistical_analysis" in intents and "run_qa" not in plan:
            plan.append("run_qa")

        state["plan"] = _dedupe_plan(plan)
        return state

    if "forecasting" in intents:
        dataset_available = _ensure_dataset_loaded(state, plan)
        
        if not dataset_available and not dataset_requested:
            state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
            state["stop"] = True
            return state
        
        plan.extend([
            "profile_data",
            "forecast_data",
            "chart_interpretation",
            "hypothesis_generation",
        ])
        state["last_operation"] = "forecast"
        state["last_chart_type"] = "forecast"
        state["plan"] = _dedupe_plan(plan)
        return state

    if "comparison" in intents:
        dataset_available = _ensure_dataset_loaded(state, plan)
        
        if not dataset_available and not dataset_requested:
            state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
            state["stop"] = True
            return state
        
        plan.extend([
            "profile_data",
            "dataset_topic_detection",
            "pattern_detection",
            "compare_datasets",
            "chart_interpretation",
            "hypothesis_generation",
        ])
        state["last_operation"] = "compare"
        state["plan"] = _dedupe_plan(plan)
        return state

    if "cleaning" in intents:
        dataset_available = _ensure_dataset_loaded(state, plan)
        
        if not dataset_available and not dataset_requested:
            state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
            state["stop"] = True
            return state

        plan.append("clean_data")
        state["last_operation"] = "clean"
        state["plan"] = _dedupe_plan(plan)
        return state

    if "explanation" in intents:
        dataset_available = _ensure_dataset_loaded(state, plan)
        
        if not dataset_available and not dataset_requested:
            state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
            state["stop"] = True
            return state
        
        plan.extend([
            "profile_data",
            "dataset_topic_detection",
            "pattern_detection",
            "explain_dataset",
            "chart_interpretation",
            "hypothesis_generation",
        ])
        if "visualization" in intents:
            plan.append("run_viz")
            state["last_chart_type"] = _detect_chart_type(normalized)
        elif "statistical_analysis" in intents:
            plan.append("run_qa")
        state["last_operation"] = "explain"
        state["plan"] = _dedupe_plan(plan)
        return state

    if "visualization" in intents:
        dataset_available = _ensure_dataset_loaded(state, plan)
        
        # Visualization should always proceed - load dataset if needed
        plan.extend([
            "profile_data",
            "run_viz",
            "chart_interpretation",
        ])
        state["last_operation"] = "visualization"
        state["last_chart_type"] = _detect_chart_type(normalized)
        state["plan"] = _dedupe_plan(plan)
        return state

    if "statistical_analysis" in intents:
        dataset_available = _ensure_dataset_loaded(state, plan)
        
        if not dataset_available and not dataset_requested:
            state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
            state["stop"] = True
            return state
        
        plan.extend([
            "profile_data",
            "dataset_topic_detection",
            "pattern_detection",
            "run_qa",
            "hypothesis_generation",
        ])
        state["last_operation"] = "statistical_analysis"
        state["plan"] = _dedupe_plan(plan)
        return state

    # Default analysis if no specific intent matched
    dataset_available = _ensure_dataset_loaded(state, plan)
    
    if not dataset_available and not dataset_requested:
        state["answer"] = "I could not determine which dataset to load. Try specifying one like GDP, population, or climate."
        state["stop"] = True
        return state
    
    plan.extend([
        "profile_data",
        "recommend_analysis",
        "dataset_topic_detection",
        "pattern_detection",
        "run_eda",
        "chart_interpretation",
        "hypothesis_generation",
    ])
    state["last_operation"] = "analyze"
    state["plan"] = _dedupe_plan(plan)
    return state

