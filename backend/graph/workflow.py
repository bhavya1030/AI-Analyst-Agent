from langgraph.graph import StateGraph, END

from backend.core.logger import get_logger
from backend.agents.planner_agent import planner_agent
from backend.agents.data_agent import data_agent

logger = get_logger(__name__)
from backend.agents.data_engineer_agent import data_engineer_agent
from backend.agents.cleaning_agent import cleaning_agent
from backend.agents.conversation_context_agent import conversation_context_agent
from backend.agents.dataset_topic_agent import dataset_topic_agent
from backend.agents.dataset_search_agent import dataset_search_agent
from backend.agents.dataset_retrieve_agent import dataset_retrieve_agent
from backend.agents.dataset_prepare_agent import dataset_prepare_agent
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
from backend.agents.chart_interpretation_agent import chart_interpretation_agent
from backend.agents.hypothesis_agent import hypothesis_agent
from backend.agents.dataset_embedding_search_agent import dataset_embedding_search_agent

ROUTE_MAP = {
    "load_data": "load_data",
    "fetch_data": "fetch_data",
    "retrieve_dataset": "retrieve_dataset",
    "prepare_dataset": "prepare_dataset",
    "profile_data": "profile_data",
    "recommend_analysis": "recommend_analysis",
    "dataset_topic_detection": "dataset_topic_detection",
    "dataset_topic_agent": "dataset_topic_agent",
    "dataset_search_agent": "dataset_search_agent",
    "pattern_detection": "pattern_detection",
    "explain_dataset": "explain_dataset",
    "clean_data": "clean_data",
    "run_eda": "run_eda",
    "run_viz": "run_viz",
    "run_multi_viz": "run_multi_viz",
    "run_qa": "run_qa",
    "forecast_data": "forecast_data",
    "chart_interpretation": "chart_interpretation",
    "hypothesis_generation": "hypothesis_generation",
    "dataset_embedding_search": "dataset_embedding_search",
    "compare_datasets": "compare_datasets",
    "generate_insight": "generate_insight",
}

REGISTERED_NODES = {
    "conversation_context",
    "planner",
    "load_data",
    "fetch_data",
    "retrieve_dataset",
    "prepare_dataset",
    "profile_data",
    "recommend_analysis",
    "dataset_topic_detection",
    "dataset_topic_agent",
    "dataset_search_agent",
    "pattern_detection",
    "explain_dataset",
    "dataset_embedding_search",
    "clean_data",
    "run_eda",
    "run_viz",
    "run_multi_viz",
    "run_qa",
    "forecast_data",
    "chart_interpretation",
    "hypothesis_generation",
    "compare_datasets",
    "generate_insight",
}

VALID_ROUTE_MAP = {
    key: target
    for key, target in ROUTE_MAP.items()
    if target in REGISTERED_NODES
}

invalid_route_entries = [
    key for key, target in ROUTE_MAP.items() if target not in REGISTERED_NODES
]
if invalid_route_entries:
    logger.warning(
        "Workflow route map contains invalid node targets",
        extra={"invalid_route_keys": invalid_route_entries},
    )


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
        logger.info(
            "Router selected terminal node",
            extra={"action": "router", "plan": plan},
        )
        return "generate_insight"

    next_node = plan[0]
    logger.info(
        "Router selected next node",
        extra={"action": "router", "next_node": next_node, "plan": plan},
    )

    if next_node in VALID_ROUTE_MAP:
        return next_node

    logger.warning(
        "Router found invalid next node, falling back",
        extra={"next_node": next_node, "plan": plan},
    )
    return "generate_insight"


def build_graph(*, checkpointer=None):
    """
    Build and compile the analysis graph.

    Phase 6: when checkpointer is None, uses SessionCheckpointer so turn state
    can be restored by session_id (thread_id).
    """
    if checkpointer is None:
        try:
            from backend.graph.checkpointer import get_session_checkpointer

            checkpointer = get_session_checkpointer()
        except Exception as exc:
            logger.warning(
                "Session checkpointer unavailable; running without persistence",
                extra={"error": str(exc)},
            )
            checkpointer = None

    builder = StateGraph(dict)

    # -------------------------
    # REGISTER NODES
    # -------------------------

    builder.add_node("conversation_context", conversation_context_agent)
    builder.add_node("planner", planner_agent)

    builder.add_node("load_data", _wrap_agent("load_data", data_agent))
    builder.add_node("fetch_data", _wrap_agent("fetch_data", data_engineer_agent))
    builder.add_node(
        "retrieve_dataset",
        _wrap_agent("retrieve_dataset", dataset_retrieve_agent),
    )
    builder.add_node(
        "prepare_dataset",
        _wrap_agent("prepare_dataset", dataset_prepare_agent),
    )

    builder.add_node("profile_data", _wrap_agent("profile_data", dataset_profile_agent))
    builder.add_node(
        "recommend_analysis",
        _wrap_agent("recommend_analysis", recommendation_agent),
    )
    builder.add_node(
        "dataset_topic_agent",
        _wrap_agent("dataset_topic_agent", dataset_topic_agent),
    )
    builder.add_node(
        "dataset_topic_detection",
        _wrap_agent("dataset_topic_detection", dataset_topic_agent),
    )
    builder.add_node(
        "dataset_search_agent",
        _wrap_agent("dataset_search_agent", dataset_search_agent),
    )
    builder.add_node(
        "pattern_detection",
        _wrap_agent("pattern_detection", pattern_detection_agent),
    )
    builder.add_node(
        "explain_dataset",
        _wrap_agent("explain_dataset", dataset_insight_agent),
    )
    builder.add_node(
        "dataset_embedding_search",
        _wrap_agent("dataset_embedding_search", dataset_embedding_search_agent),
    )

    builder.add_node("clean_data", _wrap_agent("clean_data", cleaning_agent))

    builder.add_node("run_eda", _wrap_agent("run_eda", eda_agent))
    builder.add_node("run_viz", _wrap_agent("run_viz", viz_agent))
    builder.add_node("run_multi_viz", _wrap_agent("run_multi_viz", run_multi_viz_agent))
    builder.add_node("run_qa", _wrap_agent("run_qa", qa_agent))
    builder.add_node("forecast_data", _wrap_agent("forecast_data", forecasting_agent))
    builder.add_node(
        "chart_interpretation",
        _wrap_agent("chart_interpretation", chart_interpretation_agent),
    )
    builder.add_node(
        "hypothesis_generation",
        _wrap_agent("hypothesis_generation", hypothesis_agent),
    )

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

    # All analysis nodes route through the plan-driven router so the planner
    # can compose full ChatGPT-like pipelines (discover → prepare → analyze →
    # visualize → recommend → insight) without hard-coded dead ends.
    for node_name in [
        "planner",
        "load_data",
        "fetch_data",
        "retrieve_dataset",
        "prepare_dataset",
        "profile_data",
        "recommend_analysis",
        "dataset_topic_agent",
        "dataset_topic_detection",
        "dataset_search_agent",
        "pattern_detection",
        "explain_dataset",
        "dataset_embedding_search",
        "clean_data",
        "run_eda",
        "run_viz",
        "run_multi_viz",
        "run_qa",
        "forecast_data",
        "chart_interpretation",
        "hypothesis_generation",
        "compare_datasets",
    ]:
        # Include terminal insight so stop / empty-plan routes never fail.
        edge_map = {**VALID_ROUTE_MAP, "generate_insight": "generate_insight"}
        builder.add_conditional_edges(node_name, router, edge_map)

    # -------------------------
    # TERMINAL EDGES
    # -------------------------

    builder.add_edge("generate_insight", END)

    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()
