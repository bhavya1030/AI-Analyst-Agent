"""Automatic dataset metadata generation and registry population."""

from backend.metadata.generator import generate_metadata
from backend.metadata.models import (
    PLACEHOLDER_TOPICS,
    GeneratedDatasetMetadata,
    is_placeholder_label,
)
from backend.metadata.service import (
    DatasetMetadataService,
    generate_and_register_dataset_metadata,
    get_metadata_service,
)
from backend.metadata.topic_detection import (
    detect_countries_from_text,
    detect_metrics_from_columns,
    prefer_non_placeholder,
    topic_from_columns_and_values,
    topic_from_filename,
    topic_from_question,
)

__all__ = [
    "PLACEHOLDER_TOPICS",
    "GeneratedDatasetMetadata",
    "DatasetMetadataService",
    "generate_metadata",
    "generate_and_register_dataset_metadata",
    "get_metadata_service",
    "is_placeholder_label",
    "prefer_non_placeholder",
    "topic_from_columns_and_values",
    "topic_from_filename",
    "topic_from_question",
    "detect_countries_from_text",
    "detect_metrics_from_columns",
]
