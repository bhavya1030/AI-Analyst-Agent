"""Production multi-provider open-data retrieval architecture."""

from backend.retrieval.data_providers.base import (
    DataProvider,
    DatasetCandidate,
    ProviderSearchResult,
)
from backend.retrieval.data_providers.orchestrator import (
    OrchestratorResult,
    ProviderOrchestrator,
    default_providers,
    get_provider_orchestrator,
    set_provider_orchestrator,
)
from backend.retrieval.data_providers.topic import TopicContext, extract_topic_context
from backend.retrieval.data_providers.validation import (
    is_blocked_url,
    probe_download,
    validate_download_payload,
    validate_url_metadata,
)

__all__ = [
    "DataProvider",
    "DatasetCandidate",
    "ProviderSearchResult",
    "ProviderOrchestrator",
    "OrchestratorResult",
    "default_providers",
    "get_provider_orchestrator",
    "set_provider_orchestrator",
    "TopicContext",
    "extract_topic_context",
    "is_blocked_url",
    "probe_download",
    "validate_download_payload",
    "validate_url_metadata",
]
