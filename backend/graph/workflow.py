from langgraph.graph import StateGraph, END

from backend.agents.planner_agent import planner_agent
from backend.agents.data_agent import data_agent
from backend.agents.data_engineer_agent import data_engineer_agent
from backend.agents.cleaning_agent import cleaning_agent
from backend.agents.conversation_context_agent import conversation_context_agent
from backend.agents.dataset_topic_agent import dataset_topic_agent
from backend.agents.pattern_detection_agent import pattern_detection_agent
from backend.agents.eda_agent import eda_agent
from backend.agents.viz_agent import viz_agent, run_multi_viz_agent
from backend.agents.qa_agent import qa_agent
from backend.agents.insight_agent import insight_agent
from backend.agents.dataset_profile_agent import dataset_profile_agent
from backend.agents.recommendation_agent import recommendation_agent
from backend.agents.dataset_insight_agent import dataset_insight_agent
from backend.agents.comparison_agent import comparison_agent
from backend.agents.forecasting_agent import forecasting_agent

ROUTE_MAP = {
    "load_data": "load_data",
    "fetch_data": "fetch_data",
    "profile_data": "profile_data",
    "recommend_analysis": "recommend_analysis",
    "dataset_topic_detection": "dataset_topic_detection",
    "pattern_detection": "pattern_detection",
    "explain_dataset": "explain_dataset",
    "clean_data": "clean_data",
    "run_eda": "run_eda",
    "run_viz": "run_viz",
    "run_multi_viz": "run_multi_viz",
    "run_qa": "run_qa",
    "forecast_data": "forecast_data",
    "compare_datasets": "compare_datasets",
    "generate_insight": "generate_insight",
}


def _wrap_agent(node_name, agent):
    def _runner(state):
        plan = list(state.get("plan") or [])

        if plan and plan[0] == node_name:
            state["plan"] = plan[1:]

        return agent(state)

    return _runner


def router(state):
    if state.get("stop"):
        return "generate_insight"

    plan = list(state.get("plan") or [])

    if not plan:
        return "generate_insight"

    next_node = plan[0]

    if next_node in ROUTE_MAP:
        return next_node

    return "generate_insight"


def build_graph():

    builder = StateGraph(dict)

    # -------------------------
    # REGISTER NODES
    # -------------------------

    builder.add_node("conversation_context", conversation_context_agent)
    builder.add_node("planner", planner_agent)

    builder.add_node("load_data", _wrap_agent("load_data", data_agent))
    builder.add_node("fetch_data", _wrap_agent("fetch_data", data_engineer_agent))

    builder.add_node("profile_data", _wrap_agent("profile_data", dataset_profile_agent))
    builder.add_node(
        "recommend_analysis",
        _wrap_agent("recommend_analysis", recommendation_agent),
    )
    builder.add_node(
        "dataset_topic_detection",
        _wrap_agent("dataset_topic_detection", dataset_topic_agent),
    )
    builder.add_node(
        "pattern_detection",
        _wrap_agent("pattern_detection", pattern_detection_agent),
    )
    builder.add_node(
        "explain_dataset",
        _wrap_agent("explain_dataset", dataset_insight_agent),
    )

    builder.add_node("clean_data", _wrap_agent("clean_data", cleaning_agent))

    builder.add_node("run_eda", _wrap_agent("run_eda", eda_agent))
    builder.add_node("run_viz", _wrap_agent("run_viz", viz_agent))
    builder.add_node("run_multi_viz", _wrap_agent("run_multi_viz", run_multi_viz_agent))
    builder.add_node("run_qa", _wrap_agent("run_qa", qa_agent))
    builder.add_node("forecast_data", _wrap_agent("forecast_data", forecasting_agent))

    builder.add_node(
        "compare_datasets",
        _wrap_agent("compare_datasets", comparison_agent),
    )

    builder.add_node("generate_insight", insight_agent)

    # -------------------------
    # ENTRY POINT
    # -------------------------

    builder.set_entry_point("conversation_context")
    builder.add_edge("conversation_context", "planner")

    for node_name in [
        "planner",
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
    ]:
        builder.add_conditional_edges(node_name, router, ROUTE_MAP)

    # -------------------------
    # AFTER COMPARISON AGENT
    # -------------------------

    builder.add_edge("compare_datasets", "generate_insight")

    # -------------------------
    # TERMINAL EDGES
    # -------------------------

    builder.add_edge("generate_insight", END)

    return builder.compile()
