"""Dataset Retrieval package — source decision only (no download / analysis)."""

from backend.retrieval.agent import DatasetRetrievalAgent
from backend.retrieval.exceptions import RetrievalError, RetrievalValidationError
from backend.retrieval.models import (
    DatasetRequest,
    NextAction,
    ProviderHit,
    RetrievalResult,
    RetrievalStatus,
)
from backend.retrieval.service import (
    DatasetRetrievalService,
    get_retrieval_agent,
    retrieve_dataset,
    set_retrieval_agent,
)

__all__ = [
    "DatasetRetrievalAgent",
    "DatasetRetrievalService",
    "DatasetRequest",
    "RetrievalResult",
    "RetrievalStatus",
    "NextAction",
    "ProviderHit",
    "RetrievalError",
    "RetrievalValidationError",
    "retrieve_dataset",
    "get_retrieval_agent",
    "set_retrieval_agent",
]
