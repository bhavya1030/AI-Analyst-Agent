from langgraph.graph import StateGraph, END

from backend.state import AnalystState
from backend.agents.data_agent import data_agent
from backend.agents.cleaning_agent import cleaning_agent
from backend.agents.decision_agent import decision_agent
from backend.agents.eda_agent import eda_agent
from backend.agents.qa_agent import qa_agent


def build_graph():

    graph = StateGraph(AnalystState)

    graph.add_node("load_data", data_agent)
    graph.add_node("clean_data", cleaning_agent)
    graph.add_node("run_eda", eda_agent)
    graph.add_node("run_qa", qa_agent)

    graph.set_entry_point("load_data")

    graph.add_conditional_edges(
        "load_data",
        decision_agent,
        {
            "clean_data": "clean_data",
            "skip_cleaning": "run_eda",
        },
    )

    graph.add_edge("clean_data", "run_eda")
    graph.add_edge("run_eda", "run_qa")
    graph.add_edge("run_qa", END)

    return graph.compile()