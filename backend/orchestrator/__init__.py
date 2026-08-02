"""Orchestrator package — coordinates the ask/analyze pipeline.

Modules
-------
state_builder        Build AnalystState dicts from session snapshots.
response_builder     Format raw LangGraph results into stable HTTP dicts.
request_orchestrator Coordinate the full ask/analyze pipelines (no FastAPI).
"""

from backend.orchestrator.request_orchestrator import RequestOrchestrator, get_orchestrator
from backend.orchestrator.state_builder import (
    SessionSnapshot,
    build_analyst_state,
    get_session_snapshot,
    is_remote_reference,
    normalize_dataset_reference,
)
from backend.orchestrator.response_builder import build_stable_response

__all__ = [
    "RequestOrchestrator",
    "get_orchestrator",
    "SessionSnapshot",
    "build_analyst_state",
    "get_session_snapshot",
    "is_remote_reference",
    "normalize_dataset_reference",
    "build_stable_response",
]
