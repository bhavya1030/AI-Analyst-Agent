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


def planner_agent(state):

    question = (state.get("question") or "").strip().lower()

    print("PLANNER RECEIVED QUESTION:", question)

    intents = classify_intents(question)

    print("DETECTED INTENTS:", intents)

    plan = []

    # --------------------------
    # DATASET SEARCH
    # --------------------------

    if "dataset_search" in intents:

        plan.append("fetch_data")
        plan.append("profile_data")

        if "explanation" in intents:
            plan.append("explain_dataset")
        else:
            plan.append("recommend_analysis")

        if "visualization" in intents:
            plan.append("run_viz")

        elif "statistical_analysis" in intents:
            plan.append("run_qa")

        else:
            plan.append("run_eda")

        state["plan"] = _dedupe_plan(plan)
        return state

    # --------------------------
    # AUTO ANALYSIS MODE
    # --------------------------

    if "auto_analysis" in intents:

        if _ensure_dataset_loaded(state, plan):

            plan.extend([
                "profile_data",
                "recommend_analysis",
                "run_eda",
                "run_viz",
            ])

            if "statistical_analysis" in intents:
                plan.append("run_qa")

            if "explanation" in intents:
                plan.insert(plan.index("run_eda"), "explain_dataset")

            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    # --------------------------
    # MULTI-DATASET COMPARISON
    # --------------------------

    if "comparison" in intents:
        plan.append("compare_datasets")
        state["plan"] = _dedupe_plan(plan)
        return state

    if "cleaning" in intents:

        if not _ensure_dataset_loaded(state, plan):
            state["answer"] = "Please load or fetch a dataset first."
            state["stop"] = True
            return state

        plan.append("clean_data")

    # --------------------------
    # EXPLANATION
    # --------------------------

    if "explanation" in intents:

        if _ensure_dataset_loaded(state, plan):
            if "profile_data" not in plan:
                plan.append("profile_data")
            plan.append("explain_dataset")

            if "visualization" in intents:
                plan.append("run_viz")
            elif "statistical_analysis" in intents:
                plan.append("run_qa")

            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    # --------------------------
    # VISUALIZATION
    # --------------------------

    if "visualization" in intents:

        if _ensure_dataset_loaded(state, plan):

            plan.append("profile_data")
            plan.append("run_viz")

            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    # --------------------------
    # STATISTICAL ANALYSIS
    # --------------------------

    if "statistical_analysis" in intents:

        if _ensure_dataset_loaded(state, plan):

            plan.append("run_qa")

            state["plan"] = _dedupe_plan(plan)
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    # --------------------------
    # DEFAULT EDA FLOW
    # --------------------------

    if _ensure_dataset_loaded(state, plan):

        plan.extend([
            "profile_data",
            "recommend_analysis",
            "run_eda",
        ])

        state["plan"] = _dedupe_plan(plan)
        return state

    state["answer"] = "Please load or fetch a dataset first."
    state["stop"] = True

    return state

