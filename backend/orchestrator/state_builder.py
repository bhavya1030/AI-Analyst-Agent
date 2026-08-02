"""State builder — constructs LangGraph AnalystState dicts.

Extracted verbatim from backend/main.py (_SessionSnapshot, _get_session_snapshot,
_load_session_dataset, _is_remote_reference, _normalize_dataset_reference,
_question_is_new_topic, _build_state).  Logic is identical; only location changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from backend.core.logger import get_logger
from backend.utils.dataset_loader import load_dataset

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class SessionSnapshot:
    """Lightweight session state used for state building and memory loading."""

    dataset_topic: str | None = None
    dataset_url: str | None = None
    dataset_path: str | None = None
    dataset_name: str | None = None
    # Continuity fields read by build_analyst_state
    last_column: str | None = None
    last_columns: list | None = None
    last_chart_type: str | None = None
    last_intent: str | None = None
    last_operation: str | None = None
    last_forecast_target: str | None = None
    dataset_id: str | None = None


# ---------------------------------------------------------------------------
# Session snapshot loader
# ---------------------------------------------------------------------------


def get_session_snapshot(session_id: str) -> SessionSnapshot | None:
    """Read session fields from SessionService for state building."""
    try:
        from backend.sessions.service import get_session_service

        detail = get_session_service().get_session_detail(
            session_id, include_deleted=False
        )
        return SessionSnapshot(
            dataset_topic=detail.get("dataset_topic") or None,
            dataset_url=detail.get("dataset_url") or None,
            dataset_path=detail.get("dataset_path") or None,
            dataset_name=detail.get("dataset_name") or None,
            last_column=detail.get("last_column") or None,
            last_columns=detail.get("last_columns") or None,
            last_chart_type=detail.get("last_chart_type") or None,
            last_intent=detail.get("last_intent") or None,
            last_operation=detail.get("last_operation") or None,
            last_forecast_target=detail.get("last_forecast_target") or None,
            dataset_id=detail.get("dataset_id") or None,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dataset reference helpers
# ---------------------------------------------------------------------------


def is_remote_reference(reference: str) -> bool:
    """Return True when reference is an http/https URL."""
    if not reference:
        return False
    parsed = urlparse(reference)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_dataset_reference(file_path: str | None) -> str | None:
    """Resolve a local path to an absolute string, or pass URLs through unchanged."""
    if not file_path:
        return None
    if is_remote_reference(file_path):
        return file_path
    return str(Path(file_path).expanduser().resolve(strict=False))


def _load_session_dataset(session: SessionSnapshot | None):
    """Reload the active dataset from the session's stored path/URL."""
    if session is None:
        return None

    dataset_path = getattr(session, "dataset_path", None)
    dataset_url = getattr(session, "dataset_url", None)

    if dataset_path:
        try:
            dataset = load_dataset(dataset_path)
            logger.info(
                "Session dataset reloaded",
                extra={"action": "load_session_dataset", "dataset": dataset_path},
            )
            return dataset
        except Exception as exc:
            logger.warning(
                "Failed to load session dataset path",
                extra={
                    "action": "load_session_dataset",
                    "dataset": dataset_path,
                    "error": str(exc),
                },
            )

    if dataset_url:
        try:
            dataset = load_dataset(dataset_url)
            logger.info(
                "Session dataset reloaded",
                extra={"action": "load_session_dataset", "dataset": dataset_url},
            )
            return dataset
        except Exception as exc:
            logger.warning(
                "Failed to load session dataset URL",
                extra={
                    "action": "load_session_dataset",
                    "dataset": dataset_url,
                    "error": str(exc),
                },
            )

    return None


# ---------------------------------------------------------------------------
# Core state builder
# ---------------------------------------------------------------------------


def build_analyst_state(
    session: SessionSnapshot | None,
    question: str | None = None,
    file_path: str | None = None,
) -> dict:
    """Build the AnalystState dict from session snapshot + current request.

    Mirrors the logic of the former ``_build_state`` in main.py exactly.
    """
    from backend.memory.continuity import should_reuse_session_dataset

    dataset_url = getattr(session, "dataset_url", None) if session is not None else None
    dataset_path = getattr(session, "dataset_path", None) if session is not None else None
    dataset_topic = getattr(session, "dataset_topic", None) if session is not None else None
    session_topic_for_provider = dataset_topic

    reuse, topic_mismatch = should_reuse_session_dataset(
        question=question,
        dataset_topic=dataset_topic,
        dataset_path=dataset_path,
        dataset_url=dataset_url,
        has_frame=False,
        file_path_override=file_path,
    )

    # Hard stop: "Analyze IPL" after India GDP must release the GDP file_path.
    effective_file_path = file_path
    if topic_mismatch:
        previous_topic = dataset_topic
        previous_path = file_path or dataset_path
        dataset = None
        dataset_url = None
        dataset_path = None
        effective_file_path = None  # force discovery / new bind
        dataset_topic = None
        reuse = False
        logger.info(
            "Session dataset cleared for new topic",
            extra={
                "action": "build_state",
                "previous_topic": previous_topic,
                "previous_path": previous_path,
                "question": question,
                "topic_mismatch": True,
                "file_path": None,
                "reuse_dataset": False,
            },
        )
    else:
        dataset = None if file_path else _load_session_dataset(session)
        if dataset is not None:
            reuse = True
            topic_mismatch = False

    bound_path = None if effective_file_path else dataset_path
    return {
        "data": dataset,
        "last_dataset": dataset,
        "last_column_used": getattr(session, "last_column", None) if session is not None else None,
        "last_columns_used": (getattr(session, "last_columns", None) or []) if session is not None else [],
        "last_chart_type": getattr(session, "last_chart_type", None) if session is not None else None,
        "last_intent": getattr(session, "last_intent", None) if session is not None else None,
        "last_operation": getattr(session, "last_operation", None) if session is not None else None,
        "last_forecast_target": getattr(session, "last_forecast_target", None) if session is not None else None,
        "cleaned": False,
        "insights": [],
        "question": question,
        "answer": None,
        "chart": None,
        "charts": [],
        "forecast": [],
        "forecast_chart": None,
        "forecast_error": None,
        "chart_error": None,
        "error_type": None,
        "chart_explanation": None,
        "hypotheses": [],
        "related_datasets": [],
        "plan": [],
        "dataset_profile": {},
        "dataset_explanation": [],
        "recommended_next_steps": [],
        "detected_patterns": [],
        "dataset_topic": dataset_topic,
        "dataset_url": dataset_url,
        "dataset_path": bound_path,
        "file_path": effective_file_path or bound_path,
        "local_path": (
            bound_path
            if bound_path and not str(bound_path).startswith(("http://", "https://"))
            else None
        ),
        "has_active_dataset": dataset is not None or bool(bound_path or dataset_url or effective_file_path),
        "reuse_active_dataset": bool(reuse and not topic_mismatch),
        "topic_mismatch": topic_mismatch,
        "force_reload_dataset": topic_mismatch,
        "planner_skip_upload": bool(reuse and not topic_mismatch),
        "chart_columns_used": [],
        "rows": int(dataset.shape[0]) if dataset is not None else 0,
        "columns": dataset.columns.tolist() if dataset is not None else [],
        "error": None,
        "needs_user_data": False,
        "data_acquisition_options": [],
        "dataset_discovery": {},
        "search_queries": [],
        "source": "session" if dataset is not None and not file_path else None,
        "dataset_source": None,
        "focus_country": None,
        "dataset_id": getattr(session, "dataset_id", None) if session is not None else None,
        "registry_id": None,
        "dataset_metadata": {},
        "retrieval_result": {},
        "acquisition_result": {},
        "dataset_intelligence": {},
        "learning_result": {},
        "session_dataset_topic": session_topic_for_provider,
        "memory": {},
        "conversation_memory": {},
        "session_memory": {},
        "dataset_memory": {},
        "knowledge_memory": {},
        "memory_hierarchy_loaded": False,
        "recent_messages": [],
        "selected_columns": (getattr(session, "last_columns", None) or []) if session is not None else [],
        "filters": [],
    }


def _question_is_new_topic(
    question: str | None,
    active_topic: str | None,
    *,
    has_active_dataset: bool = False,
) -> bool:
    """True when the user named a different subject than the session dataset.

    Alias kept so tests that previously imported this from backend.main
    continue to work after Phase 3 moved it to state_builder.
    """
    from backend.memory.continuity import is_new_dataset_topic

    return is_new_dataset_topic(
        question,
        active_topic,
        has_active_dataset=has_active_dataset,
    )
