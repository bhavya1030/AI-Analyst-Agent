from langgraph.graph import StateGraph, END

from backend.agents.planner_agent import planner_agent
from backend.agents.data_agent import data_agent
from backend.agents.data_engineer_agent import data_engineer_agent
from backend.agents.cleaning_agent import cleaning_agent
from backend.agents.eda_agent import eda_agent
from backend.agents.viz_agent import viz_agent
from backend.agents.qa_agent import qa_agent
from backend.agents.insight_agent import insight_agent
from backend.agents.dataset_profile_agent import dataset_profile_agent
from backend.agents.recommendation_agent import recommendation_agent


def router(state):

    if state.get("stop"):
        return "generate_insight"

    plan = state.get("plan", [])

    if not plan:
        return "generate_insight"

    return plan.pop(0)


def build_graph():

    builder = StateGraph(dict)

    # Nodes
    builder.add_node("planner", planner_agent)
    builder.add_node("load_data", data_agent)
    builder.add_node("fetch_data", data_engineer_agent)
    builder.add_node("profile_data", dataset_profile_agent)
    builder.add_node("recommend_analysis", recommendation_agent)
    builder.add_node("clean_data", cleaning_agent)
    builder.add_node("run_eda", eda_agent)
    builder.add_node("run_viz", viz_agent)
    builder.add_node("run_qa", qa_agent)
    builder.add_node("generate_insight", insight_agent)

    builder.set_entry_point("planner")

    # Planner routing
    builder.add_conditional_edges(
        "planner",
        router,
        {
            "load_data": "load_data",
            "fetch_data": "fetch_data",
            "profile_data": "profile_data",
            "recommend_analysis": "recommend_analysis",
            "run_eda": "run_eda",
            "run_viz": "run_viz",
            "run_qa": "run_qa",
            "generate_insight": "generate_insight",
        },
    )

    # After loading dataset
    builder.add_conditional_edges(
        "load_data",
        router,
        {
            "profile_data": "profile_data",
            "run_eda": "run_eda",
            "run_viz": "run_viz",
            "run_qa": "run_qa",
            "generate_insight": "generate_insight",
        },
    )

    # After fetching dataset
    builder.add_conditional_edges(
        "fetch_data",
        router,
        {
            "profile_data": "profile_data",
            "run_eda": "run_eda",
            "run_viz": "run_viz",
            "run_qa": "run_qa",
            "generate_insight": "generate_insight",
        },
    )

    # Sequential intelligence pipeline
    builder.add_edge("profile_data", "recommend_analysis")
    builder.add_edge("recommend_analysis", "run_eda")

    builder.add_edge("run_eda", "generate_insight")
    builder.add_edge("run_viz", "generate_insight")
    builder.add_edge("run_qa", "generate_insight")

    builder.add_edge("generate_insight", END)

    return builder.compile()