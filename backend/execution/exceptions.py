"""Exceptions for Multi-Dataset Execution Engine."""

from __future__ import annotations


class ExecutionError(Exception):
    """Base error for multi-dataset execution."""


class ExecutionValidationError(ExecutionError):
    """Invalid input to the execution engine."""


class SchemaAlignmentError(ExecutionError):
    """Schema alignment failed (usually non-fatal; surfaced as warnings)."""


class MergeError(ExecutionError):
    """Dataset merge/join failed."""


class DatasetPipelineError(ExecutionError):
    """Single-dataset retrieve/acquire/profile/learn pipeline failed."""

    def __init__(self, topic: str, message: str, *, optional: bool = True):
        self.topic = topic
        self.optional = optional
        super().__init__(f"[{topic}] {message}")
