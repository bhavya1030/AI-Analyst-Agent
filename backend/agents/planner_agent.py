from backend.utils.intent_classifier import classify_intents

def planner_agent(state):

    question = state.get("question", "").lower()

    print("PLANNER RECEIVED QUESTION:", question)

    intents = classify_intents(question)

    print("DETECTED INTENTS:", intents)

    dataset_available = state.get("data") is not None

    plan = []

    # --------------------------
    # DATASET SEARCH INTENT
    # --------------------------

    if "dataset_search" in intents:

        plan.append("fetch_data")

        if "visualization" in intents:
            plan.append("run_viz")

        elif "statistical_analysis" in intents:
            plan.append("run_qa")

        else:
            plan.append("run_eda")

        state["plan"] = plan
        return state


    # --------------------------
    # VISUALIZATION INTENT
    # --------------------------

    if "visualization" in intents:

        if dataset_available:

            plan.append("run_viz")

            state["plan"] = plan
            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True

        return state


    # --------------------------
    # STATISTICS INTENT
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
    # DEFAULT → EDA
    # --------------------------

    if dataset_available:

        plan.append("run_eda")

        state["plan"] = plan
        return state


    state["answer"] = "Please load or fetch a dataset first."
    state["stop"] = True

    return state