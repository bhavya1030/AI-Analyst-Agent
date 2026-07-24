"""Errors for Dataset Retrieval Agent (decision layer only)."""


class RetrievalError(Exception):
    """Base retrieval error."""


class RetrievalValidationError(RetrievalError):
    """Invalid retrieval request."""
