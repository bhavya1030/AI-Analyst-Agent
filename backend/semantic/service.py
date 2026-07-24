"""Semantic Dataset Search service.

Indexes registry dataset text fields and searches by similarity.
Does not perform retrieval orchestration or modify LangGraph.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from backend.core.logger import get_logger
from backend.semantic.embedding_generator import (
    EmbeddingGenerator,
    HashingEmbeddingGenerator,
    SentenceTransformerEmbeddingGenerator,
    create_default_embedding_generator,
)
from backend.semantic.exceptions import SemanticValidationError
from backend.semantic.models import (
    SemanticDocument,
    SemanticSearchResult,
    build_index_text,
)
from backend.semantic.vector_store import (
    VectorStore,
    create_default_vector_store,
)

logger = get_logger(__name__)

_default_service: "SemanticSearchService | None" = None


class SemanticSearchService:
    """
    Public API:
      index_dataset()
      search_similar()
      delete_dataset()
      update_dataset()
    """

    def __init__(
        self,
        *,
        embedder: EmbeddingGenerator | None = None,
        store: VectorStore | None = None,
        auto_persist: bool = True,
    ):
        self._embedder = embedder or create_default_embedding_generator()
        dim = getattr(self._embedder, "dimension", 384) or 384
        self._store = store or create_default_vector_store(dimension=int(dim))
        self.auto_persist = auto_persist

    def index_dataset(self, registry_entry: Any) -> str:
        """
        Embed and upsert a registry entry (or dict-like metadata).

        Returns registry_id (also used as embedding identity / embedding_ref candidate).
        """
        meta = _normalize_registry_entry(registry_entry)
        registry_id = meta.get("dataset_id") or meta.get("registry_id")
        if not registry_id:
            raise SemanticValidationError("registry_entry requires dataset_id / registry_id")

        text = build_index_text(
            title=str(meta.get("title") or ""),
            description=str(meta.get("description") or ""),
            tags=list(meta.get("tags") or []),
            topic_keywords=list(
                meta.get("topic_keywords")
                or _keywords_from_topic(meta.get("topic"))
                or []
            ),
            summary=str(meta.get("summary") or ""),
            topic=str(meta.get("topic") or ""),
        )
        if not text.strip():
            text = str(registry_id)

        vector = self._embedder.embed_one(text)
        document = SemanticDocument(
            registry_id=str(registry_id),
            text=text,
            metadata={
                "dataset_id": str(registry_id),
                "title": meta.get("title"),
                "topic": meta.get("topic"),
                "description": meta.get("description"),
                "tags": meta.get("tags") or [],
                "summary": meta.get("summary"),
                "source": meta.get("source"),
                "download_url": meta.get("download_url"),
                "local_path": meta.get("local_path"),
                "file_format": meta.get("file_format"),
            },
        )
        self._store.upsert(str(registry_id), vector, document)
        if self.auto_persist:
            self._safe_save()
        logger.info(
            "Semantic index upsert",
            extra={"registry_id": registry_id, "text_len": len(text)},
        )
        return str(registry_id)

    def search_similar(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.25,
    ) -> list[SemanticSearchResult]:
        """Semantic search over indexed datasets."""
        q = (query or "").strip()
        if not q:
            raise SemanticValidationError("query is required")
        vector = self._embedder.embed_one(q)
        results = self._store.search(vector, top_k=top_k, min_score=min_score)
        logger.info(
            "Semantic search complete",
            extra={"query": q[:80], "hits": len(results)},
        )
        return results

    def delete_dataset(self, registry_id: str) -> bool:
        if not registry_id:
            return False
        deleted = self._store.delete(str(registry_id))
        if deleted and self.auto_persist:
            self._safe_save()
        return deleted

    def update_dataset(self, registry_entry: Any) -> str:
        """Re-embed and replace an existing entry (same as index upsert)."""
        return self.index_dataset(registry_entry)

    def _safe_save(self) -> None:
        try:
            self._store.save()
        except Exception as exc:
            logger.warning("Semantic store save failed", extra={"error": str(exc)})


def _normalize_registry_entry(entry: Any) -> dict[str, Any]:
    if entry is None:
        return {}
    if isinstance(entry, dict):
        return dict(entry)
    if hasattr(entry, "to_dict"):
        try:
            return dict(entry.to_dict())
        except Exception:
            pass
    keys = [
        "dataset_id",
        "registry_id",
        "title",
        "topic",
        "description",
        "tags",
        "summary",
        "source",
        "download_url",
        "local_path",
        "file_format",
        "topic_keywords",
        "columns",
    ]
    out: dict[str, Any] = {}
    for k in keys:
        if hasattr(entry, k):
            out[k] = getattr(entry, k)
    return out


def _keywords_from_topic(topic: Any) -> list[str]:
    if not topic:
        return []
    return [t for t in str(topic).replace("_", " ").split() if len(t) > 2]


def get_semantic_service(
    *,
    use_hashing_embeddings: bool = False,
) -> SemanticSearchService:
    """Process-wide default service (lazy)."""
    global _default_service
    if _default_service is None:
        if use_hashing_embeddings:
            embedder = HashingEmbeddingGenerator()
            from backend.semantic.vector_store import NumpyVectorStore, default_vector_store_path

            store = NumpyVectorStore(
                default_vector_store_path().with_suffix(".test.npy.pkl"),
                dimension=embedder.dimension,
            )
            try:
                store.load()
            except Exception:
                pass
            _default_service = SemanticSearchService(embedder=embedder, store=store)
        else:
            _default_service = SemanticSearchService()
    return _default_service


def set_semantic_service(service: SemanticSearchService | None) -> None:
    global _default_service
    _default_service = service


# Module-level API


def index_dataset(registry_entry: Any) -> str:
    return get_semantic_service().index_dataset(registry_entry)


def search_similar(
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.25,
) -> list[SemanticSearchResult]:
    return get_semantic_service().search_similar(query, top_k=top_k, min_score=min_score)


def delete_dataset(registry_id: str) -> bool:
    return get_semantic_service().delete_dataset(registry_id)


def update_dataset(registry_entry: Any) -> str:
    return get_semantic_service().update_dataset(registry_entry)
