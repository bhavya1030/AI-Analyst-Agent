def planner_agent(state):

    question = state.get("question", "").lower()

    print("PLANNER RECEIVED QUESTION:", question)

    plan = []

    dataset_keywords = [
        "find dataset",
        "fetch dataset",
        "download dataset",
        "get dataset",
        "dataset about",
    ]

    viz_keywords = [
        "plot",
        "chart",
        "graph",
        "distribution",
        "scatter",
        "bar",
        "pie",
        "line",
        "box",
        "heatmap",
        "correlation",
        "vs",
        "trend",
        "histogram",
    ]

    stat_keywords = [
        "average",
        "mean",
        "max",
        "min",
        "count",
        "median",
        "std",
        "variance",
        "sum"
    ]

    dataset_requested = any(k in question for k in dataset_keywords)
    viz_requested = any(k in question for k in viz_keywords)
    stat_requested = any(k in question for k in stat_keywords)

    dataset_available = state.get("data") is not None


    # -------------------------------
    # CASE 1: dataset requested
    # -------------------------------

    if dataset_requested:

        plan.append("fetch_data")

        if viz_requested:
            plan.append("run_viz")

        elif stat_requested:
            plan.append("run_qa")

        else:
            plan.append("run_eda")

        state["plan"] = plan
        print("PLANNER ROUTE:", plan)

        return state


    # -------------------------------
    # CASE 2: stats request
    # -------------------------------

    if stat_requested:

        if dataset_available:

            plan.append("run_qa")

            state["plan"] = plan
            print("PLANNER ROUTE:", plan)

            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True

        return state


    # -------------------------------
    # CASE 3: visualization request
    # -------------------------------

    if viz_requested:

        if dataset_available:

            plan.append("run_viz")

            state["plan"] = plan
            print("PLANNER ROUTE:", plan)

            return state

        state["answer"] = "Please load or fetch a dataset first."
        state["stop"] = True

        return state


    # -------------------------------
    # DEFAULT CASE
    # -------------------------------

    if dataset_available:

        plan.append("run_eda")

        state["plan"] = plan
        print("PLANNER ROUTE:", plan)

        return state


    state["answer"] = "Please load or fetch a dataset first."
    state["stop"] = True

    return state