"""Errors for Semantic Dataset Search."""


class SemanticError(Exception):
    """Base semantic search error."""


class SemanticValidationError(SemanticError):
    """Invalid index/search input."""


class EmbeddingError(SemanticError):
    """Embedding generation failed."""


class VectorStoreError(SemanticError):
    """Vector index operation failed."""
