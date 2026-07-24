"""Embedding generation hook for future semantic search.

Not implemented yet — Learning Service calls this after registry upsert.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from backend.registry.models import DatasetMetadata


class EmbeddingGenerator(ABC):
    """
    Future pipeline:

        Dataset → Profile → EmbeddingGenerator → Learning Service → Registry

    Implementations should return an embedding_ref (vector store id / path),
    not raw vectors into the registry row (registry stores the reference only).
    """

    name: str = "base"

    @abstractmethod
    def generate(self, metadata: DatasetMetadata, *, profile: Optional[dict[str, Any]] = None) -> Optional[str]:
        """Return embedding_ref or None if skipped."""
        ...


class NoOpEmbeddingGenerator(EmbeddingGenerator):
    """Default: do nothing (Task 9 — no embeddings yet)."""

    name = "noop"

    def generate(self, metadata: DatasetMetadata, *, profile: Optional[dict[str, Any]] = None) -> Optional[str]:
        return None
