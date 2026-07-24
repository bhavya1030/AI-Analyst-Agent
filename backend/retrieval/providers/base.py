"""Abstract retrieval provider interface.

Future providers (Official API, Internet Search, User Upload) implement this
without changing DatasetRetrievalAgent orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.retrieval.models import DatasetRequest, ProviderHit


class RetrievalProvider(ABC):
    """A single source checked by the Retrieval Agent."""

    name: str = "base"

    @abstractmethod
    def try_retrieve(self, request: DatasetRequest) -> Optional[ProviderHit]:
        """
        Attempt to resolve the request from this source.

        Returns:
            ProviderHit if this provider can answer (hit, stale, etc.)
            None if this provider has nothing to say (caller tries next).
        """
        ...
