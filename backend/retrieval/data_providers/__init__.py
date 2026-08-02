"""Production multi-provider open-data retrieval architecture (v3)."""

from backend.retrieval.data_providers.base import (
    DataProvider,
    DatasetCandidate,
    ProviderSearchResult,
)
from backend.retrieval.data_providers.eurostat import EurostatProvider
from backend.retrieval.data_providers.fred import FredProvider
from backend.retrieval.data_providers.orchestrator import (
    OrchestratorResult,
    ProviderOrchestrator,
    default_providers,
    get_provider_orchestrator,
    set_provider_orchestrator,
)
from backend.retrieval.data_providers.provider_circuit import (
    is_provider_available,
    provider_circuit_status,
    record_provider_failure,
    record_provider_success,
    reset_provider_circuits,
)
from backend.retrieval.data_providers.ranking import PROVIDER_TRUST, rank_candidates
from backend.retrieval.data_providers.timeout_budget import (
    is_retryable_error,
    new_budget,
    run_with_timeout,
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
    "FredProvider",
    "EurostatProvider",
    "default_providers",
    "get_provider_orchestrator",
    "set_provider_orchestrator",
    "TopicContext",
    "extract_topic_context",
    "is_blocked_url",
    "probe_download",
    "validate_download_payload",
    "validate_url_metadata",
    "rank_candidates",
    "PROVIDER_TRUST",
    "new_budget",
    "run_with_timeout",
    "is_retryable_error",
    "is_provider_available",
    "record_provider_success",
    "record_provider_failure",
    "provider_circuit_status",
    "reset_provider_circuits",
]
