"""Multi-Dataset Execution Engine.

Execute DatasetRequest[] via existing Retrieval → Acquisition → Intelligence → Learning,
then align schemas and merge into a unified DataFrame for Data Engineer.
"""

from backend.execution.dataset_merger import DatasetMerger
from backend.execution.exceptions import (
    DatasetPipelineError,
    ExecutionError,
    ExecutionValidationError,
    MergeError,
    SchemaAlignmentError,
)
from backend.execution.execution_engine import ExecutionEngine, execute_datasets
from backend.execution.models import (
    ColumnRoleHints,
    DatasetExecStatus,
    ExecutionResult,
    JoinStrategy,
    MergeResult,
    ProcessedDataset,
    SchemaAlignmentResult,
)
from backend.execution.schema_alignment import (
    SchemaAlignmentService,
    canonicalize_column_name,
    detect_column_roles,
    detect_common_columns,
)

__all__ = [
    # Engine
    "ExecutionEngine",
    "execute_datasets",
    # Alignment / merge
    "SchemaAlignmentService",
    "DatasetMerger",
    "canonicalize_column_name",
    "detect_column_roles",
    "detect_common_columns",
    # Models
    "ExecutionResult",
    "ProcessedDataset",
    "SchemaAlignmentResult",
    "MergeResult",
    "ColumnRoleHints",
    "JoinStrategy",
    "DatasetExecStatus",
    # Exceptions
    "ExecutionError",
    "ExecutionValidationError",
    "SchemaAlignmentError",
    "MergeError",
    "DatasetPipelineError",
]
