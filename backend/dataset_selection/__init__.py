"""Dataset Selection — choose best candidate among multiple datasets."""

from backend.dataset_selection.models import (
    DatasetCandidate,
    SelectionInput,
    SelectionResult,
)
from backend.dataset_selection.prompts import build_selection_prompt
from backend.dataset_selection.selector import (
    DatasetSelector,
    LLMDatasetSelector,
    RuleBasedSelector,
    get_default_selector,
    select_best_dataset,
    set_default_selector,
)

__all__ = [
    "DatasetSelector",
    "RuleBasedSelector",
    "LLMDatasetSelector",
    "DatasetCandidate",
    "SelectionInput",
    "SelectionResult",
    "select_best_dataset",
    "get_default_selector",
    "set_default_selector",
    "build_selection_prompt",
]
