from typing import TypedDict, Optional
import pandas as pd


class AnalystState(TypedDict):
    data: Optional[pd.DataFrame]
    cleaned: bool
    insights: list
    question: Optional[str]
    answer: Optional[str]
    chart: Optional[str]