"""Conversation Context Manager — multi-turn memory and reference resolution.

Stores dataset/filter/viz/analysis *references* only (never DataFrames).
Planner is not modified; ResolvedRequest is the future planner input.
"""

from backend.context.context_manager import (
    ConversationContextManager,
    clear_context,
    get_context_manager,
    load_context,
    reset_context_manager,
    resolve_reference,
    save_context,
    update_context,
)
from backend.context.conversation_memory import (
    DEFAULT_TTL_SECONDS,
    ConversationMemoryStore,
    get_default_store,
    reset_default_store,
)
from backend.context.exceptions import (
    ContextError,
    ContextExpiredError,
    ContextNotFoundError,
    ContextValidationError,
    ReferenceResolutionError,
)
from backend.context.models import (
    AnalysisStep,
    ConversationContext,
    DatasetRef,
    FilterSpec,
    ReferenceKind,
    ResolvedReference,
    ResolvedRequest,
    VisualizationRef,
)
from backend.context.reference_resolver import ReferenceResolver

__all__ = [
    # Manager API
    "ConversationContextManager",
    "get_context_manager",
    "reset_context_manager",
    "save_context",
    "load_context",
    "update_context",
    "resolve_reference",
    "clear_context",
    # Memory
    "ConversationMemoryStore",
    "get_default_store",
    "reset_default_store",
    "DEFAULT_TTL_SECONDS",
    # Resolver
    "ReferenceResolver",
    # Models
    "ConversationContext",
    "DatasetRef",
    "FilterSpec",
    "VisualizationRef",
    "AnalysisStep",
    "ResolvedRequest",
    "ResolvedReference",
    "ReferenceKind",
    # Exceptions
    "ContextError",
    "ContextValidationError",
    "ContextNotFoundError",
    "ContextExpiredError",
    "ReferenceResolutionError",
]
