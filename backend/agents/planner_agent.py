from backend.utils.intent_classifier import classify_intents


def _ensure_dataset_loaded(state, plan):
    if state.get("data") is not None:
        return True

    if state.get("file_path"):
        if "load_data" not in plan:
            plan.append("load_data")
        return True

    return False


def _dedupe_plan(plan):
    deduped = []
    for step in plan:
        if step not in deduped:
            deduped.append(step)
    return deduped


def _detect_chart_type(question: str) -> str:
    if "heatmap" in question or "correlation" in question:
        return "heatmap"
    if "scatter" in question or "vs" in question:
        return "scatter"
    if "line" in question or "trend" in question:
        return "line"
    if "box" in question:
        return "box"
    return "visualization"


def planner_agent(state):
    question = (state.get("question") or "").strip()
    normalized = question.lower()

    print("PLANNER RECEIVED QUESTION:", question)

    intents = classify_intents(normalized)

    print("DETECTED INTENTS:", intents)

    profile = state.get("dataset_profile") or {}
    numeric_cols = profile.get("numeric_columns", [])
    categorical_cols = profile.get("categorical_columns", [])
    time_cols = profile.get("time_columns", [])

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

        if "explanation" in intents:
            plan.append("explain_dataset")
            state["last_operation"] = "explain"
        else:
            plan.append("recommend_analysis")
            state["last_operation"] = "recommend"

        if "visualization" in intents:
            plan.append("run_viz")
            state["last_chart_type"] = _detect_chart_type(normalized)
        elif "statistical_analysis" in intents:
            plan.append("run_qa")
            state["last_operation"] = "statistical_analysis"
        else:
            plan.append("run_eda")
            state["last_operation"] = "analyze"

        state["plan"] = _dedupe_plan(plan)
        return state

    if "auto_analysis" in intents or "analyze dataset" in normalized:
        if _ensure_dataset_loaded(state, plan):
            plan.extend([
                "profile_data",
                "recommend_analysis",
                "dataset_topic_detection",
                "pattern_detection",
                "run_eda",
                "run_multi_viz",
            ])

            if "statistical_analysis" in intents:
                plan.append("run_qa")

            if "explanation" in intents:
                plan.insert(plan.index("run_eda"), "explain_dataset")

            state["last_operation"] = "analyze"
            state["last_chart_type"] = "multi"
            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    if "forecasting" in intents:
        if _ensure_dataset_loaded(state, plan):
            plan.extend([
                "profile_data",
                "forecast_data",
                "generate_insight",
            ])
            state["last_operation"] = "forecast"
            state["last_chart_type"] = "forecast"
            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    if "comparison" in intents:
        if _ensure_dataset_loaded(state, plan):
            plan.extend([
                "profile_data",
                "dataset_topic_detection",
                "pattern_detection",
                "compare_datasets",
            ])
            state["last_operation"] = "compare"
            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    if "cleaning" in intents:
        if not _ensure_dataset_loaded(state, plan):
            state["answer"] = "Please load or fetch a dataset first."
            state["stop"] = True
            return state

        plan.append("clean_data")
        state["last_operation"] = "clean"
        state["plan"] = _dedupe_plan(plan)
        return state

    if "explanation" in intents:
        if _ensure_dataset_loaded(state, plan):
            plan.extend([
                "profile_data",
                "dataset_topic_detection",
                "pattern_detection",
                "explain_dataset",
            ])
            if "visualization" in intents:
                plan.append("run_viz")
                state["last_chart_type"] = _detect_chart_type(normalized)
            elif "statistical_analysis" in intents:
                plan.append("run_qa")
            state["last_operation"] = "explain"
            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    if "visualization" in intents:
        if _ensure_dataset_loaded(state, plan):
            plan.extend([
                "profile_data",
                "dataset_topic_detection",
                "pattern_detection",
                "run_viz",
            ])
            state["last_operation"] = "visualization"
            state["last_chart_type"] = _detect_chart_type(normalized)
            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    if "statistical_analysis" in intents:
        if _ensure_dataset_loaded(state, plan):
            plan.extend([
                "profile_data",
                "dataset_topic_detection",
                "pattern_detection",
                "run_qa",
            ])
            state["last_operation"] = "statistical_analysis"
            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    if _ensure_dataset_loaded(state, plan):
        plan.extend([
            "profile_data",
            "recommend_analysis",
            "dataset_topic_detection",
            "pattern_detection",
            "run_eda",
        ])
        state["last_operation"] = "analyze"
        state["plan"] = _dedupe_plan(plan)
        return state

    state["answer"] = "Please load or fetch a dataset first."
    state["stop"] = True
    return state

