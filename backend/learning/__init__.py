"""Dataset Learning — write acquired+profiled datasets into the Registry."""

from backend.learning.embeddings import EmbeddingGenerator, NoOpEmbeddingGenerator
from backend.learning.exceptions import (
    LearningError,
    LearningRegistryError,
    LearningValidationError,
)
from backend.learning.models import LearningAction, LearningInput, LearningResult
from backend.learning.service import DatasetLearningService, learn_dataset

__all__ = [
    "DatasetLearningService",
    "learn_dataset",
    "LearningResult",
    "LearningAction",
    "LearningInput",
    "EmbeddingGenerator",
    "NoOpEmbeddingGenerator",
    "LearningError",
    "LearningValidationError",
    "LearningRegistryError",
]
