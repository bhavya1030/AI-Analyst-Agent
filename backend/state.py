from typing import Any, Optional, TypedDict
import pandas as pd


class AnalystState(TypedDict, total=False):
    data: Optional[pd.DataFrame]
    last_dataset: Optional[pd.DataFrame]
    cleaned: bool
    insights: list
    question: Optional[str]
    answer: Optional[str]
    chart: Optional[dict[str, Any]]
    plan: list
    file_path: Optional[str]
    dataset_url: Optional[str]
    dataset_profile: dict[str, Any]
    dataset_explanation: list[str]
    recommended_next_steps: list[str]
    detected_patterns: list[str]
    dataset_topic: Optional[str]
    last_column_used: Optional[str]
    last_columns_used: list[str]
    last_chart_type: Optional[str]
    last_intent: Optional[str]
    last_operation: Optional[str]
    last_forecast_target: Optional[str]
    chart_columns_used: list[str]
    charts: list[dict[str, Any]]
    chart_explanation: Optional[str]
    hypotheses: list[str]
    related_datasets: list[dict[str, Any]]
    rows: int
    columns: list[str]
    error: Optional[str]
    stop: bool
    needs_user_data: bool
    data_acquisition_options: list[dict[str, Any]]
    dataset_discovery: dict[str, Any]
    search_queries: list[str]
    source: Optional[str]
    dataset_source: Optional[str]
    # New data pipeline (retrieval → prepare → engineer)
    local_path: Optional[str]
    dataset_id: Optional[str]
    registry_id: Optional[str]
    dataset_metadata: dict[str, Any]
    retrieval_result: dict[str, Any]
    acquisition_result: dict[str, Any]
    dataset_intelligence: dict[str, Any]
    learning_result: dict[str, Any]
    session_dataset_topic: Optional[str]
    # Phase 5 — hierarchical memory (injected each request)
    session_id: Optional[str]
    dataset_fingerprint: Optional[str]
    memory: dict[str, Any]
    conversation_memory: dict[str, Any]
    session_memory: dict[str, Any]
    dataset_memory: dict[str, Any]
    knowledge_memory: dict[str, Any]
    memory_hierarchy_loaded: bool
    recent_messages: list
    conversation_summary: Optional[str]
    preferred_columns: list[str]
    preferred_chart_types: list[str]
    prior_dataset_insights: list[str]
    dataset_memory_key: Optional[str]
    dataset_prior_analysis_count: int
    knowledge_topic_hint: Optional[str]
