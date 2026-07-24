"""Placeholder: User upload / paste-URL provider — not implemented yet."""

from __future__ import annotations

from typing import Optional

from backend.retrieval.models import DatasetRequest, ProviderHit
from backend.retrieval.providers.base import RetrievalProvider


class UserUploadProvider(RetrievalProvider):
    """Future: handle explicit user upload path or pasted URL. Always None for now."""

    name = "user_upload"

    def try_retrieve(self, request: DatasetRequest) -> Optional[ProviderHit]:
        # Intentionally unimplemented.
        return None
