"""Session Memory provider — read-only check of current session binding."""

from __future__ import annotations

import re
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.retrieval.models import DatasetRequest, ProviderHit, RetrievalStatus
from backend.retrieval.providers.base import RetrievalProvider

logger = get_logger(__name__)


def _tokens(text: str) -> set[str]:
    stop = {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by",
        "data", "dataset", "rate", "rates", "price", "prices",
    }
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 2 and t not in stop
    }


def topics_compatible(requested: str, session_topic: str | None) -> bool:
    """True if requested topic matches the session's active dataset topic."""
    req = (requested or "").strip().lower()
    ses = (session_topic or "").strip().lower()
    if not req:
        return False
    if not ses:
        # Session has data but no topic label — allow only empty/generic reuse
        return False
    if req == ses or req in ses or ses in req:
        return True
    r_tok, s_tok = _tokens(req), _tokens(ses)
    if not r_tok or not s_tok:
        return False
    return bool(r_tok & s_tok)


class SessionProvider(RetrievalProvider):
    """
    Priority step 1: Session Memory.

    Does not load DataFrames. Only inspects session snapshot fields
    (from request or DB session_memory row).
    """

    name = "session"

    def __init__(self, session_loader=None):
        """
        session_loader: optional callable(session_id) -> object with
        dataset_topic, dataset_url, dataset_path attributes (e.g. db.get_session).
        """
        self._session_loader = session_loader

    def try_retrieve(self, request: DatasetRequest) -> Optional[ProviderHit]:
        if request.force_new_topic:
            return None

        snapshot = self._resolve_snapshot(request)
        if snapshot is None:
            return None

        topic = request.normalized_topic()
        session_topic = snapshot.get("topic")
        if not topics_compatible(topic, session_topic):
            return None

        has_binding = bool(
            snapshot.get("has_active_data")
            or snapshot.get("local_path")
            or snapshot.get("download_url")
            or snapshot.get("dataset_id")
        )
        if not has_binding:
            return None

        metadata = {
            "topic": session_topic,
            "download_url": snapshot.get("download_url"),
            "local_path": snapshot.get("local_path"),
            "source": "session_memory",
            "source_type": "Session",
            "title": session_topic or topic,
            "session_id": snapshot.get("session_id"),
        }

        logger.info(
            "SessionProvider hit",
            extra={"topic": topic, "session_topic": session_topic},
        )
        return ProviderHit(
            status=RetrievalStatus.SESSION_HIT,
            dataset_id=snapshot.get("dataset_id"),
            local_path=snapshot.get("local_path"),
            download_url=snapshot.get("download_url"),
            metadata=metadata,
            reason=f"Session already bound to topic '{session_topic}'.",
            provider_name=self.name,
        )

    def _resolve_snapshot(self, request: DatasetRequest) -> Optional[dict[str, Any]]:
        # Prefer explicit in-request session fields (LangGraph state)
        if (
            request.has_active_data
            or request.session_dataset_url
            or request.session_local_path
            or request.session_dataset_id
            or request.session_topic
        ):
            return {
                "session_id": request.session_id,
                "topic": request.session_topic,
                "download_url": request.session_dataset_url,
                "local_path": request.session_local_path,
                "dataset_id": request.session_dataset_id,
                "has_active_data": request.has_active_data,
            }

        if not request.session_id or self._session_loader is None:
            return None

        try:
            row = self._session_loader(request.session_id)
        except Exception as exc:
            logger.warning(
                "SessionProvider failed to load session",
                extra={"session_id": request.session_id, "error": str(exc)},
            )
            return None

        if row is None:
            return None

        topic = getattr(row, "dataset_topic", None)
        url = getattr(row, "dataset_url", None)
        path = getattr(row, "dataset_path", None)
        if not any([topic, url, path]):
            return None

        return {
            "session_id": request.session_id,
            "topic": topic,
            "download_url": url,
            "local_path": path,
            "dataset_id": None,
            "has_active_data": bool(url or path),
        }
