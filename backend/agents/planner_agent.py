def planner_agent(state):

    question = state.get("question", "").lower()

    plan = ["load_data"]

    if any(word in question for word in ["clean", "missing", "null"]):
        plan.append("clean_data")

    if any(word in question for word in ["summary", "describe", "analyze", "structure"]):
        plan.append("run_eda")

    if any(word in question for word in ["plot", "chart", "graph", "distribution", "trend"]):
        plan.append("run_viz")

    if any(word in question for word in ["average", "mean", "max", "min", "count"]):
        plan.append("run_qa")

    if len(plan) == 1:
        plan.append("run_eda")

    state["plan"] = plan

    return state