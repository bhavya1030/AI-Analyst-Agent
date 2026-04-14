from backend.utils.intent_classifier import classify_intents


def planner_agent(state):

    question = state.get("question", "").lower()

    print("PLANNER RECEIVED QUESTION:", question)

    intents = classify_intents(question)

    print("DETECTED INTENTS:", intents)

    dataset_available = state.get("data") is not None

    plan = []

    # --------------------------
    # DATASET SEARCH
    # --------------------------

    if "dataset_search" in intents:

        plan.append("fetch_data")
        plan.append("profile_data")
        plan.append("recommend_analysis")

        if "visualization" in intents:
            plan.append("run_viz")

        elif "statistical_analysis" in intents:
            plan.append("run_qa")

        else:
            plan.append("run_eda")

        state["plan"] = plan
        return state

    # --------------------------
    # AUTO ANALYSIS MODE
    # --------------------------

    if "auto_analysis" in intents:

        if dataset_available:

            plan.extend([
                "profile_data",
                "recommend_analysis",
                "run_eda",
                "run_viz",
                "generate_insight"
            ])

            state["plan"] = plan
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    # --------------------------
    # VISUALIZATION
    # --------------------------

    if "visualization" in intents:

        if dataset_available:

            plan.append("profile_data")
            plan.append("run_viz")

            state["plan"] = plan
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    # --------------------------
    # STATISTICAL ANALYSIS
    # --------------------------

    if "statistical_analysis" in intents:

        if dataset_available:

            plan.append("run_qa")

            state["plan"] = plan
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True
        return state

    # --------------------------
    # DEFAULT EDA FLOW
    # --------------------------

    if dataset_available:

        plan.extend([
            "profile_data",
            "recommend_analysis",
            "run_eda",
            "generate_insight"
        ])

        state["plan"] = plan
        return state

    state["answer"] = "Please load or fetch a dataset first."
    state["stop"] = True

    return state