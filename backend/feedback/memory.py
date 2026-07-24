"""Thread-safe feedback memory store (process-local, RLHF-ready records)."""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Optional

from backend.core.logger import get_logger
from backend.feedback.models import FeedbackQuery, FeedbackRecord, FeedbackType

logger = get_logger(__name__)


class FeedbackMemory:
    """
    In-memory store of FeedbackRecord entries.

    Future: swap for durable backend (SQLite / preference DB) without
    changing FeedbackService API.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._records: list[FeedbackRecord] = []
        self._by_id: dict[str, FeedbackRecord] = {}

    def add(self, record: FeedbackRecord) -> FeedbackRecord:
        if not record.feedback_id:
            raise ValueError("feedback_id required")
        with self._lock:
            stored = deepcopy(record)
            self._records.append(stored)
            self._by_id[stored.feedback_id] = stored
            logger.debug(
                "Feedback stored",
                extra={
                    "feedback_id": stored.feedback_id,
                    "type": stored.feedback.value
                    if isinstance(stored.feedback, FeedbackType)
                    else stored.feedback,
                },
            )
            return deepcopy(stored)

    def get(self, feedback_id: str) -> Optional[FeedbackRecord]:
        with self._lock:
            rec = self._by_id.get((feedback_id or "").strip())
            return deepcopy(rec) if rec else None

    def list(
        self,
        query: FeedbackQuery | None = None,
    ) -> list[FeedbackRecord]:
        query = query or FeedbackQuery()
        with self._lock:
            items = list(self._records)

        if query.user:
            u = query.user.strip().lower()
            items = [r for r in items if (r.user or "").lower() == u]
        if query.feedback_type:
            ft = query.feedback_type
            items = [r for r in items if r.feedback == ft]
        if query.question_contains:
            q = query.question_contains.lower()
            items = [r for r in items if q in (r.question or "").lower()]
        if query.dataset_key:
            key = query.dataset_key.lower()
            items = [r for r in items if key in _dataset_key(r).lower()]
        if query.conversation_id:
            cid = query.conversation_id
            items = [r for r in items if r.conversation_id == cid]
        if query.since:
            items = [r for r in items if (r.timestamp or "") >= query.since]

        # Newest first
        items.sort(key=lambda r: r.timestamp or "", reverse=True)
        limit = max(1, int(query.limit or 100))
        return [deepcopy(r) for r in items[:limit]]

    def all(self) -> list[FeedbackRecord]:
        with self._lock:
            return [deepcopy(r) for r in self._records]

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> int:
        with self._lock:
            n = len(self._records)
            self._records.clear()
            self._by_id.clear()
            return n


def _dataset_key(record: FeedbackRecord) -> str:
    ds = record.chosen_dataset or {}
    if isinstance(ds, dict):
        return str(
            ds.get("dataset_id")
            or ds.get("topic")
            or ds.get("title")
            or ds.get("local_path")
            or ""
        )
    return str(ds)


_default_memory: FeedbackMemory | None = None
_mem_lock = threading.Lock()


def get_default_memory() -> FeedbackMemory:
    global _default_memory
    with _mem_lock:
        if _default_memory is None:
            _default_memory = FeedbackMemory()
        return _default_memory


def reset_default_memory() -> None:
    global _default_memory
    with _mem_lock:
        if _default_memory is not None:
            _default_memory.clear()
        _default_memory = None
