from langgraph.graph import StateGraph, END

from backend.state import AnalystState

from backend.agents.planner_agent import planner_agent
from backend.agents.data_agent import data_agent
from backend.agents.cleaning_agent import cleaning_agent
from backend.agents.eda_agent import eda_agent
from backend.agents.qa_agent import qa_agent
from backend.agents.viz_agent import viz_agent
from backend.agents.insight_agent import insight_agent


def build_graph():

    graph = StateGraph(AnalystState)

    # Register nodes
    graph.add_node("planner", planner_agent)
    graph.add_node("load_data", data_agent)
    graph.add_node("clean_data", cleaning_agent)
    graph.add_node("run_eda", eda_agent)
    graph.add_node("run_qa", qa_agent)
    graph.add_node("run_viz", viz_agent)
    graph.add_node("generate_insight", insight_agent)

    # Entry point
    graph.set_entry_point("planner")

    # Planner decides execution order
    def route(state):
        return state["plan"][0]

    graph.add_conditional_edges(
        "planner",
        route,
        {
            "load_data": "load_data",
            "clean_data": "clean_data",
            "run_eda": "run_eda",
            "run_qa": "run_qa",
            "run_viz": "run_viz",
        },
    )

    # Continue execution chain automatically
    graph.add_edge("load_data", "run_eda")
    graph.add_edge("clean_data", "run_eda")

    graph.add_edge("run_eda", "generate_insight")
    graph.add_edge("generate_insight", END)

    graph.add_edge("run_viz", END)
    graph.add_edge("run_qa", END)

    return graph.compile()