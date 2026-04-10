from langgraph.graph import StateGraph, END

from backend.agents.planner_agent import planner_agent
from backend.agents.data_agent import data_agent
from backend.agents.data_engineer_agent import data_engineer_agent
from backend.agents.cleaning_agent import cleaning_agent
from backend.agents.eda_agent import eda_agent
from backend.agents.viz_agent import viz_agent
from backend.agents.qa_agent import qa_agent
from backend.agents.insight_agent import insight_agent
from langgraph.graph import END
from langgraph.graph import END


def router(state):

    # restore dataset memory BEFORE routing
    if state.get("data") is None and state.get("last_dataset") is not None:
        state["data"] = state["last_dataset"]

    # persist dataset memory AFTER steps
    if state.get("data") is not None:
        state["last_dataset"] = state["data"]

    plan = state.get("plan", [])

    if not plan:
        return END

    return plan.pop(0)


def build_graph():

    builder = StateGraph(dict)

    # Nodes
    builder.add_node("planner", planner_agent)
    builder.add_node("load_data", data_agent)
    builder.add_node("fetch_data", data_engineer_agent)
    builder.add_node("clean_data", cleaning_agent)
    builder.add_node("run_eda", eda_agent)
    builder.add_node("run_viz", viz_agent)
    builder.add_node("run_qa", qa_agent)
    builder.add_node("generate_insight", insight_agent)

    # Entry point
    builder.set_entry_point("planner")

    # Dynamic routing
    builder.add_conditional_edges(
        "planner",
        router,
        {
            "load_data": "load_data",
            "fetch_data": "fetch_data",
            "run_viz": "run_viz",
            "run_eda": "run_eda",
            "run_qa": "run_qa",
        },
    )

    builder.add_conditional_edges(
        "load_data",
        router,
        {
            "run_eda": "run_eda",
            "run_viz": "run_viz",
            "run_qa": "run_qa",
        },
    )

    builder.add_conditional_edges(
        "fetch_data",
        router,
        {
            "run_eda": "run_eda",
            "run_viz": "run_viz",
            "run_qa": "run_qa",
        },
    )

    builder.add_edge("run_eda", "generate_insight")
    builder.add_edge("run_viz", "generate_insight")
    builder.add_edge("run_qa", "generate_insight")

    builder.add_edge("generate_insight", END)

    return builder.compile()