from langgraph.graph import StateGraph, END

from backend.state import AnalystState

from backend.agents.data_agent import data_agent
from backend.agents.cleaning_agent import cleaning_agent
from backend.agents.eda_agent import eda_agent
from backend.agents.qa_agent import qa_agent
from backend.agents.viz_agent import viz_agent
from backend.agents.intent_agent import intent_agent


def build_graph():

    graph = StateGraph(AnalystState)

    graph.add_node("load_data", data_agent)
    graph.add_node("clean_data", cleaning_agent)
    graph.add_node("run_eda", eda_agent)
    graph.add_node("run_qa", qa_agent)
    graph.add_node("run_viz", viz_agent)

    graph.set_entry_point("load_data")

    graph.add_conditional_edges(
        "load_data",
        intent_agent,
        {
            "clean_data": "clean_data",
            "run_eda": "run_eda",
            "run_qa": "run_qa",
            "run_viz": "run_viz",
        },
    )

    graph.add_edge("clean_data", END)
    graph.add_edge("run_eda", END)
    graph.add_edge("run_qa", END)
    graph.add_edge("run_viz", END)

    return graph.compile()