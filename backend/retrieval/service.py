"""Service façade for Dataset Retrieval Agent.

Wires default Session + Registry providers. Placeholders for future providers
are included in the chain but return None until implemented.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.core.logger import get_logger
from backend.retrieval.agent import DatasetRetrievalAgent
from backend.retrieval.models import DatasetRequest, RetrievalResult
from backend.retrieval.providers.open_data_provider import OpenDataProvider
from backend.retrieval.providers.registry_provider import RegistryProvider
from backend.retrieval.providers.semantic_provider import SemanticProvider
from backend.retrieval.providers.session_provider import SessionProvider
from backend.retrieval.providers.user_upload_provider import UserUploadProvider

logger = get_logger(__name__)

_default_agent: DatasetRetrievalAgent | None = None


def _build_default_agent() -> DatasetRetrievalAgent:
    # Lazy imports keep optional deps local and tests injectable
    from backend.dataset_library import dataset_exists, get_dataset_path
    from backend.db import get_session
    from backend.registry import get_by_dataset_id, get_by_topic
    from backend.semantic import search_similar

    session_provider = SessionProvider(session_loader=get_session)
    registry_provider = RegistryProvider(
        get_by_topic=get_by_topic,
        get_by_dataset_id=get_by_dataset_id,
        dataset_exists=dataset_exists,
        get_dataset_path=get_dataset_path,
    )
    semantic_provider = SemanticProvider(
        search_similar=search_similar,
        get_by_dataset_id=get_by_dataset_id,
        dataset_exists=dataset_exists,
        get_dataset_path=get_dataset_path,
    )

    # OpenDataProvider: multi-provider chain with URL/content validation.
    # Replaces OfficialApi + InternetSearch HTML search pages (OECD 403, etc.).
    providers = [
        session_provider,
        registry_provider,  # exact / topic match
        semantic_provider,  # embedding similarity (SEMANTIC_HIT)
        OpenDataProvider(),  # World Bank / OWID / GitHub raw / JSON APIs / data.gov / HF / CSV URLs
        UserUploadProvider(),  # placeholder
    ]
    return DatasetRetrievalAgent(providers=providers)


def get_retrieval_agent() -> DatasetRetrievalAgent:
    global _default_agent
    if _default_agent is None:
        _default_agent = _build_default_agent()
    return _default_agent


def set_retrieval_agent(agent: DatasetRetrievalAgent | None) -> None:
    """Inject agent for tests. Pass None to rebuild the default provider chain."""
    global _default_agent
    _default_agent = agent


class DatasetRetrievalService:
    """Thin service wrapper around DatasetRetrievalAgent."""

    def __init__(self, agent: DatasetRetrievalAgent | None = None):
        self._agent = agent or get_retrieval_agent()

    def retrieve(self, request: DatasetRequest | dict[str, Any]) -> RetrievalResult:
        return self._agent.retrieve(request)

    def retrieve_by_topic(
        self,
        topic: str,
        *,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> RetrievalResult:
        payload = {"topic": topic, "session_id": session_id, **kwargs}
        return self.retrieve(payload)


def retrieve_dataset(request: DatasetRequest | dict[str, Any]) -> RetrievalResult:
    """Module-level entrypoint for future Planner / LangGraph wiring."""
    return DatasetRetrievalService().retrieve(request)
