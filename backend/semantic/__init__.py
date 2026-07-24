"""Semantic Dataset Search — embeddings + vector index for registry datasets."""

from backend.semantic.embedding_generator import (
    EmbeddingGenerator,
    HashingEmbeddingGenerator,
    SentenceTransformerEmbeddingGenerator,
    create_default_embedding_generator,
)
from backend.semantic.exceptions import (
    EmbeddingError,
    SemanticError,
    SemanticValidationError,
    VectorStoreError,
)
from backend.semantic.models import SemanticDocument, SemanticSearchResult, build_index_text
from backend.semantic.service import (
    SemanticSearchService,
    delete_dataset,
    get_semantic_service,
    index_dataset,
    search_similar,
    set_semantic_service,
    update_dataset,
)
from backend.semantic.vector_store import (
    FAISSVectorStore,
    NumpyVectorStore,
    VectorStore,
    create_default_vector_store,
)

__all__ = [
    "SemanticSearchService",
    "SemanticSearchResult",
    "SemanticDocument",
    "build_index_text",
    "EmbeddingGenerator",
    "SentenceTransformerEmbeddingGenerator",
    "HashingEmbeddingGenerator",
    "create_default_embedding_generator",
    "VectorStore",
    "FAISSVectorStore",
    "NumpyVectorStore",
    "create_default_vector_store",
    "index_dataset",
    "search_similar",
    "delete_dataset",
    "update_dataset",
    "get_semantic_service",
    "set_semantic_service",
    "SemanticError",
    "SemanticValidationError",
    "EmbeddingError",
    "VectorStoreError",
]
