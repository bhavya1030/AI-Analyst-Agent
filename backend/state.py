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
    last_column_used: Optional[str]
    last_columns_used: list[str]
    chart_columns_used: list[str]
    rows: int
    columns: list[str]
    error: Optional[str]
    stop: bool
