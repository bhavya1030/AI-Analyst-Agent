"""Models for Multi-Dataset Execution Engine.

No EDA, charts, or statistics — orchestration + aligned/merged frames only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

import pandas as pd


class JoinStrategy(str, Enum):
    """How multiple datasets should be combined."""

    AUTO = "auto"
    INNER = "inner"
    LEFT = "left"
    OUTER = "outer"
    CONCAT = "concat"


class DatasetExecStatus(str, Enum):
    """Per-dataset pipeline outcome."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PARTIAL = "partial"  # local file obtained but profile/learn soft-failed


@dataclass
class ProcessedDataset:
    """Result of running retrieve → acquire → profile → learn for one request."""

    topic: str
    status: DatasetExecStatus = DatasetExecStatus.FAILED
    local_path: Optional[str] = None
    dataset_id: Optional[str] = None
    retrieval: Optional[dict[str, Any]] = None
    acquisition: Optional[dict[str, Any]] = None
    profile: Optional[dict[str, Any]] = None
    learning: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    optional: bool = True
    row_count: Optional[int] = None
    columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "status": self.status.value if isinstance(self.status, DatasetExecStatus) else self.status,
            "local_path": self.local_path,
            "dataset_id": self.dataset_id,
            "retrieval": self.retrieval,
            "acquisition": self.acquisition,
            "profile": self.profile,
            "learning": self.learning,
            "error": self.error,
            "warnings": list(self.warnings),
            "optional": self.optional,
            "row_count": self.row_count,
            "columns": list(self.columns),
        }


@dataclass
class ColumnRoleHints:
    """Detected semantic roles for columns across one or more frames."""

    common_columns: list[str] = field(default_factory=list)
    entity_columns: list[str] = field(default_factory=list)
    time_columns: list[str] = field(default_factory=list)
    country_columns: list[str] = field(default_factory=list)
    state_columns: list[str] = field(default_factory=list)
    metric_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SchemaAlignmentResult:
    """Outcome of normalizing columns across datasets."""

    aligned_frames: list[pd.DataFrame] = field(default_factory=list)
    rename_maps: list[dict[str, str]] = field(default_factory=list)
    role_hints: ColumnRoleHints = field(default_factory=ColumnRoleHints)
    join_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rename_maps": self.rename_maps,
            "role_hints": self.role_hints.to_dict(),
            "join_keys": list(self.join_keys),
            "warnings": list(self.warnings),
            "topics": list(self.topics),
            "frame_shapes": [list(df.shape) for df in self.aligned_frames],
            "frame_columns": [list(df.columns) for df in self.aligned_frames],
        }


@dataclass
class MergeResult:
    """Outcome of joining/merging aligned frames."""

    dataframe: Optional[pd.DataFrame] = None
    strategy: JoinStrategy = JoinStrategy.AUTO
    join_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    datasets_merged: int = 0

    def to_dict(self) -> dict[str, Any]:
        df = self.dataframe
        return {
            "strategy": self.strategy.value if isinstance(self.strategy, JoinStrategy) else self.strategy,
            "join_keys": list(self.join_keys),
            "warnings": list(self.warnings),
            "datasets_merged": self.datasets_merged,
            "shape": list(df.shape) if df is not None else None,
            "columns": list(df.columns) if df is not None else [],
        }


@dataclass
class ExecutionResult:
    """Final multi-dataset execution outcome for downstream Data Engineer."""

    success: bool
    datasets_processed: list[ProcessedDataset] = field(default_factory=list)
    local_paths: list[str] = field(default_factory=list)
    merged_dataframe: Optional[pd.DataFrame] = None
    join_strategy: JoinStrategy = JoinStrategy.AUTO
    join_keys: list[str] = field(default_factory=list)
    schema_alignment: Optional[dict[str, Any]] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    execution_time: float = 0.0  # seconds
    topics_requested: list[str] = field(default_factory=list)
    topics_succeeded: list[str] = field(default_factory=list)
    topics_failed: list[str] = field(default_factory=list)

    def to_dict(self, *, include_dataframe: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.success,
            "datasets_processed": [d.to_dict() for d in self.datasets_processed],
            "local_paths": list(self.local_paths),
            "join_strategy": (
                self.join_strategy.value
                if isinstance(self.join_strategy, JoinStrategy)
                else self.join_strategy
            ),
            "join_keys": list(self.join_keys),
            "schema_alignment": self.schema_alignment,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "execution_time": self.execution_time,
            "topics_requested": list(self.topics_requested),
            "topics_succeeded": list(self.topics_succeeded),
            "topics_failed": list(self.topics_failed),
            "merged_shape": (
                list(self.merged_dataframe.shape) if self.merged_dataframe is not None else None
            ),
            "merged_columns": (
                list(self.merged_dataframe.columns) if self.merged_dataframe is not None else []
            ),
        }
        if include_dataframe and self.merged_dataframe is not None:
            payload["merged_dataframe"] = self.merged_dataframe
        return payload
