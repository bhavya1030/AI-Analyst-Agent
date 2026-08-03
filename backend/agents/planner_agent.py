import json

from backend.config import settings
from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm
from backend.utils.intent_classifier import classify_intents

logger = get_logger(__name__)

VALID_PLANNER_NODES = {
    "load_data",
    "fetch_data",
    "retrieve_dataset",
    "prepare_dataset",
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
    "housing",
    "literacy",
    "cryptocurrency",
    "bitcoin",
    "oil",
    "gold",
    "silver",
    "agriculture",
    "traffic",
    "crime",
    "http://",
    "https://",
]

# Phrases that mean: discover open data for whatever topic the user named.
OPEN_WORLD_PHRASES = [
    "analyze ",
    "analyse ",
    "study ",
    "explore ",
    "investigate ",
    "dataset about",
    "data on ",
    "data about ",
    "find data",
    "open data",
    "find dataset",
    "search for data",
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
        "dataset_topic_detection": "retrieve_dataset",
        "dataset_topic_agent": "retrieve_dataset",
        "dataset_search": "prepare_dataset",
        "dataset_search_agent": "prepare_dataset",
    }
    return [mapping.get(step, step) for step in plan]


def _build_llm_plan(question: str, dataset_available: bool) -> list[str]:
    prompt = f"""
You are an analytics workflow planner for an AI Data Analyst.

Available steps:
- retrieve_dataset
- prepare_dataset
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
- If no dataset is available, start with retrieve_dataset -> prepare_dataset -> fetch_data.
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
    """Steps to discover and load data when nothing is active or topic changed.

    New pipeline: retrieve_dataset → prepare_dataset → fetch_data
    (Retrieval / Acquisition / Intelligence / Learning live behind prepare.)
    """
    if state.get("data") is not None and not force:
        return []
    # User upload is only preferred when we are not switching topics.
    if state.get("file_path") and not force and not state.get("topic_mismatch"):
        return ["load_data", "fetch_data"]
    return [
        "retrieve_dataset",
        "prepare_dataset",
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


def _needs_rediscovery(state, dataset_requested: bool) -> bool:
    """True when active data should NOT be reused for this question."""
    if state.get("data") is None and not (
        state.get("file_path") or state.get("local_path") or state.get("dataset_url")
    ):
        return False
    if state.get("topic_mismatch"):
        return True
    if state.get("force_reload_dataset") and state.get("topic_mismatch"):
        return True
    # Memory v2: planner must never re-request upload when a valid frame is bound.
    if state.get("planner_skip_upload") or state.get("reuse_active_dataset"):
        return False
    if state.get("data") is not None and not state.get("topic_mismatch"):
        # Follow-up analysis on the same session dataset
        return False
    # New named topic / open-world ask while another dataset is loaded.
    if dataset_requested and not state.get("reuse_active_dataset"):
        if state.get("data") is not None and not state.get("topic_mismatch"):
            return False
        return True
    return False


def _forecast_suffix() -> list[str]:
    return [
        "profile_data",
        "forecast_data",
        "chart_interpretation",
        "recommend_analysis",
        "generate_insight",
    ]


def _build_rule_based_plan(state, normalized, intents, dataset_requested):
    has_data = state.get("data") is not None
    has_binding = has_data or bool(
        state.get("file_path") or state.get("local_path") or state.get("dataset_url")
    )
    # Memory v2: prefer reuse whenever session data is bound and topic matches
    reuse = (
        has_binding
        and not state.get("topic_mismatch")
        and (
            bool(state.get("reuse_active_dataset"))
            or bool(state.get("planner_skip_upload"))
            or has_data
        )
    )
    rediscover = _needs_rediscovery(state, dataset_requested)

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

        plan = _discovery_prefix(state, force=rediscover)
        # Comparison agent can load its own sources; still profile when data exists.
        if (has_data and not rediscover) or plan:
            plan = plan + ["profile_data"]
        plan.extend(["compare_datasets", "recommend_analysis", "generate_insight"])
        return plan

    # --- Forecasting ---
    if "forecasting" in intents or "forecast" in intents:
        if not has_data and not dataset_requested and not state.get("dataset_url"):
            state["answer"] = (
                "I could not determine which dataset to forecast. "
                "Try specifying one like GDP, population, or climate — "
                "or analyze a dataset first, then say 'forecast it'."
            )
            state["stop"] = True
            return []

        # Only reuse active data for true follow-ups ("forecast it"), never for a new subject.
        if reuse and not rediscover:
            return _forecast_suffix()

        return _discovery_prefix(state, force=rediscover or not has_data) + [
            "clean_data",
            *_forecast_suffix(),
        ]

    # --- Explicit visualization ---
    if "visualization" in intents and "eda" not in intents and "dataset_autoload" not in intents and "dataset_switch" not in intents:
        if reuse and not rediscover:
            return [
                "profile_data",
                "run_viz",
                "chart_interpretation",
                "recommend_analysis",
                "generate_insight",
            ]
        return _discovery_prefix(state, force=rediscover or not has_data) + [
            "clean_data",
            "profile_data",
            "run_viz",
            "chart_interpretation",
            "recommend_analysis",
            "generate_insight",
        ]

    # --- Statistical QA ---
    if ("statistical_analysis" in intents or "statistics" in intents) and "eda" not in intents:
        if reuse and not rediscover:
            return ["profile_data", "run_qa", "recommend_analysis", "generate_insight"]
        return _discovery_prefix(state, force=rediscover or not has_data) + [
            "clean_data",
            "profile_data",
            "run_qa",
            "recommend_analysis",
            "generate_insight",
        ]

    # --- Full auto analysis (default ChatGPT-like path) ---
    # Covers: analyze X, dataset_autoload, eda, explanation, open-ended topics
    if reuse and not rediscover:
        return ["profile_data"] + _analysis_suffix(include_viz=True)
    if has_data and not dataset_requested and not rediscover:
        return ["profile_data"] + _analysis_suffix(include_viz=True)

    # Discovery + full analysis pipeline (open data when possible)
    plan = _discovery_prefix(state) + _analysis_suffix(include_viz=True)

    # If user also asked for a chart explicitly, multi-viz is optional; run_viz is enough.
    if "visualization" in intents and "run_viz" not in plan:
        plan.insert(-2, "run_viz")

    # Explicit forecasting alongside analysis of a new topic.
    if ("forecasting" in intents or "forecast" in intents) and "forecast_data" not in plan:
        if "generate_insight" in plan:
            plan.insert(plan.index("generate_insight"), "forecast_data")
        else:
            plan.append("forecast_data")

    return plan


def planner_agent(state: dict) -> dict:
    """
    Phase 5 — Pure Intent Router.

    Rules:
    - Checks active dataset status in session.
    - Routes to discovery ONLY for explicit dataset_switch or dataset_search intents,
      or when no dataset exists in session for an analytical query.
    - Active dataset + analytical intent ALWAYS routes directly to analysis nodes.
    """
    print(
        f"""==================================================
PLANNER INPUT
Question: {state.get("question")}
Intent: {state.get("last_intent") or state.get("intent")}
Dataset Topic: {state.get("dataset_topic")}
Active Dataset: {state.get("dataset_name") or state.get("dataset_topic")}
Dataset Path: {state.get("dataset_path") or state.get("file_path") or state.get("local_path")}
Dataset Name: {state.get("dataset_name")}
==================================================""",
        flush=True,
    )

    question = (state.get("question") or "").strip()
    normalized = question.lower()

    logger.info(
        "Planner received question",
        extra={
            "action": "plan",
            "question": question,
            "dataset": state.get("dataset_url") or state.get("file_path") or state.get("dataset_path"),
            "has_data": state.get("data") is not None,
        },
    )

    intents = state.get("intents") or classify_intents(question)
    state["intents"] = intents
    primary_intent = intents[0] if intents else "eda"
    state["last_intent"] = primary_intent

    # Opt-in LLM planner when enabled in settings
    if bool(getattr(settings, "USE_LLM_PLANNER", False)) and not state.get("stop"):
        dataset_avail = bool(
            state.get("data") is not None
            or state.get("dataset_path")
            or state.get("file_path")
            or state.get("dataset_url")
        )
        llm_plan = _build_llm_plan(question, dataset_avail)
        if llm_plan:
            state["plan"] = _dedupe_plan(llm_plan)
            state["last_operation"] = primary_intent
            return state

    # Check session active dataset binding
    has_frame = state.get("data") is not None
    has_file = bool(state.get("file_path") or state.get("local_path"))
    has_binding = bool(
        has_frame
        or state.get("dataset_path")
        or has_file
        or state.get("dataset_url")
        or state.get("active_dataset")
        or state.get("planner_skip_upload")
    )
    is_switch = bool(
        ("dataset_switch" in intents or state.get("topic_mismatch"))
        and not (has_file and not state.get("topic_mismatch"))
    )

    # 1. Explicit Dataset Switch Intent (when switching to a new topic)
    if is_switch:
        state["reuse_active_dataset"] = False
        state["force_reload_dataset"] = True
        plan = [
            "retrieve_dataset",
            "prepare_dataset",
            "fetch_data",
            "clean_data",
            "profile_data",
            "run_eda",
            "pattern_detection",
            "run_viz",
            "chart_interpretation",
            "hypothesis_generation",
            "recommend_analysis",
            "generate_insight",
        ]
        if "comparison" in intents and "compare_datasets" not in plan:
            plan.insert(plan.index("recommend_analysis"), "compare_datasets")
        state["plan"] = _dedupe_plan(plan)
        state["last_operation"] = "dataset_switch"
        return state

    # 2. Explicit Dataset Search Intent -> route to dataset search
    if "dataset_search" in intents:
        state["reuse_active_dataset"] = False
        plan = [
            "retrieve_dataset",
            "prepare_dataset",
            "fetch_data",
            "profile_data",
            "run_eda",
            "generate_insight",
        ]
        if "comparison" in intents and "compare_datasets" not in plan:
            plan.insert(plan.index("generate_insight"), "compare_datasets")
        state["plan"] = _dedupe_plan(plan)
        state["last_operation"] = "dataset_search"
        return state

    # 3. Active Dataset / File EXISTS + Analytical Intent -> Direct Analysis Nodes
    if has_binding:
        state["reuse_active_dataset"] = True
        state["planner_skip_upload"] = True
        state["needs_user_data"] = False

        load_prefix = ["load_data", "fetch_data"] if (has_file and not has_frame) else []

        if "preview" in intents:
            plan = load_prefix + ["profile_data", "run_eda", "generate_insight"]
        elif "forecast" in intents or "forecasting" in intents:
            plan = load_prefix + _forecast_suffix()
        elif "visualization" in intents:
            plan = load_prefix + [
                "profile_data",
                "run_viz",
                "chart_interpretation",
                "recommend_analysis",
                "generate_insight",
            ]
        elif "comparison" in intents:
            plan = load_prefix + [
                "profile_data",
                "compare_datasets",
                "recommend_analysis",
                "generate_insight",
            ]
        elif "statistics" in intents or "statistical_analysis" in intents or "qa" in intents:
            plan = load_prefix + [
                "profile_data",
                "run_qa",
                "recommend_analysis",
                "generate_insight",
            ]
        elif "chart_explanation" in intents:
            plan = load_prefix + ["chart_interpretation", "generate_insight"]
        else:
            plan = load_prefix + ["profile_data"] + _analysis_suffix(include_viz=True)

        if "run_viz" in plan:
            state["last_chart_type"] = _detect_chart_type(normalized)

        if "comparison" in intents and "compare_datasets" not in plan:
            idx = plan.index("generate_insight") if "generate_insight" in plan else len(plan)
            plan.insert(idx, "compare_datasets")

        state["plan"] = _dedupe_plan(plan)
        state["last_operation"] = primary_intent
        logger.info(
            "Planner produced execution plan",
            extra={"action": "plan", "plan": state["plan"], "intents": intents},
        )
        return state

    # 4. Active Dataset DOES NOT EXIST + Analytical Intent -> Trigger Data Acquisition / Discovery
    prefix = ["retrieve_dataset", "prepare_dataset", "fetch_data"]

    if "forecast" in intents or "forecasting" in intents:
        plan = prefix + ["clean_data"] + _forecast_suffix()
    elif "comparison" in intents:
        plan = prefix + [
            "profile_data",
            "compare_datasets",
            "recommend_analysis",
            "generate_insight",
        ]
    elif "visualization" in intents:
        plan = prefix + [
            "clean_data",
            "profile_data",
            "run_viz",
            "chart_interpretation",
            "recommend_analysis",
            "generate_insight",
        ]
    elif "statistics" in intents or "statistical_analysis" in intents or "qa" in intents:
        plan = prefix + [
            "clean_data",
            "profile_data",
            "run_qa",
            "recommend_analysis",
            "generate_insight",
        ]
    else:
        plan = prefix + _analysis_suffix(include_viz=True)

    if "run_viz" in plan:
        state["last_chart_type"] = _detect_chart_type(normalized)

    if "comparison" in intents and "compare_datasets" not in plan:
        idx = plan.index("generate_insight") if "generate_insight" in plan else len(plan)
        plan.insert(idx, "compare_datasets")

    state["plan"] = _dedupe_plan(plan)
    state["last_operation"] = primary_intent
    logger.info(
        "Planner produced execution plan",
        extra={"action": "plan", "plan": state["plan"], "intents": intents},
    )
    return state
