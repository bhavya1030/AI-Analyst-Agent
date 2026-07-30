"""Product memory: learned datasets + hierarchical session/dataset memory."""

from backend.memory.hierarchy import MemoryHierarchyService, get_memory_hierarchy
from backend.memory.continuity import (
    build_planner_injection,
    is_follow_up_question,
    is_new_dataset_topic,
    should_reuse_session_dataset,
)
from backend.memory.restore import apply_restored_frame, restore_dataframe
from backend.memory.learned_datasets import (
    learn_dataset,
    list_learned_datasets,
    recall_datasets,
)

__all__ = [
    "learn_dataset",
    "recall_datasets",
    "list_learned_datasets",
    "MemoryHierarchyService",
    "get_memory_hierarchy",
    "build_planner_injection",
    "is_follow_up_question",
    "is_new_dataset_topic",
    "should_reuse_session_dataset",
    "apply_restored_frame",
    "restore_dataframe",
]
