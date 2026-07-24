"""In-process multi-conversation memory store with inactivity expiry.

Does not store DataFrames. Thread-safe for concurrent conversations.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.context.exceptions import (
    ContextExpiredError,
    ContextNotFoundError,
    ContextValidationError,
)
from backend.context.models import ConversationContext, _utc_now_iso
from backend.core.logger import get_logger

logger = get_logger(__name__)

# Default: 30 minutes of inactivity
DEFAULT_TTL_SECONDS = 30 * 60


def _parse_iso(ts: str | None) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Support trailing Z
        cleaned = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


class ConversationMemoryStore:
    """
    Multi-conversation store keyed by conversation_id.

    - Supports many conversations simultaneously
    - Expires entries after ``ttl_seconds`` of inactivity
    - Returns deep copies so callers cannot mutate store state by accident
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        if ttl_seconds <= 0:
            raise ContextValidationError("ttl_seconds must be positive")
        self._ttl_seconds = int(ttl_seconds)
        self._lock = threading.RLock()
        self._store: dict[str, ConversationContext] = {}

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def set_ttl(self, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ContextValidationError("ttl_seconds must be positive")
        with self._lock:
            self._ttl_seconds = int(ttl_seconds)

    def put(self, context: ConversationContext) -> ConversationContext:
        if not context or not context.conversation_id:
            raise ContextValidationError("context.conversation_id is required")
        with self._lock:
            context.touch()
            self._store[context.conversation_id] = deepcopy(context)
            logger.debug(
                "Context stored",
                extra={"conversation_id": context.conversation_id},
            )
            return deepcopy(self._store[context.conversation_id])

    def get(
        self,
        conversation_id: str,
        *,
        touch: bool = True,
        raise_if_missing: bool = True,
        raise_if_expired: bool = True,
    ) -> Optional[ConversationContext]:
        cid = (conversation_id or "").strip()
        if not cid:
            raise ContextValidationError("conversation_id is required")

        with self._lock:
            ctx = self._store.get(cid)
            if ctx is not None and self._is_expired(ctx):
                del self._store[cid]
                # Opportunistically purge other expired conversations
                self._purge_expired_unlocked()
                if raise_if_expired:
                    raise ContextExpiredError(cid)
                return None

            # Keep store tidy without masking this id's missing/expired state
            self._purge_expired_unlocked()
            ctx = self._store.get(cid)
            if ctx is None:
                if raise_if_missing:
                    raise ContextNotFoundError(f"No context for conversation_id={cid}")
                return None

            if touch:
                ctx.touch()
                self._store[cid] = ctx

            return deepcopy(ctx)

    def delete(self, conversation_id: str) -> bool:
        cid = (conversation_id or "").strip()
        if not cid:
            raise ContextValidationError("conversation_id is required")
        with self._lock:
            existed = cid in self._store
            self._store.pop(cid, None)
            return existed

    def exists(self, conversation_id: str) -> bool:
        cid = (conversation_id or "").strip()
        if not cid:
            return False
        with self._lock:
            self._purge_expired_unlocked()
            ctx = self._store.get(cid)
            if ctx is None:
                return False
            if self._is_expired(ctx):
                del self._store[cid]
                return False
            return True

    def list_ids(self) -> list[str]:
        with self._lock:
            self._purge_expired_unlocked()
            return list(self._store.keys())

    def clear_all(self) -> int:
        with self._lock:
            n = len(self._store)
            self._store.clear()
            return n

    def count(self) -> int:
        with self._lock:
            self._purge_expired_unlocked()
            return len(self._store)

    def purge_expired(self) -> int:
        with self._lock:
            return self._purge_expired_unlocked()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_expired(self, ctx: ConversationContext) -> bool:
        last = _parse_iso(ctx.last_activity_at) or _parse_iso(ctx.updated_at)
        if last is None:
            return False
        now = datetime.now(timezone.utc)
        return now - last > timedelta(seconds=self._ttl_seconds)

    def _purge_expired_unlocked(self) -> int:
        expired = [cid for cid, ctx in self._store.items() if self._is_expired(ctx)]
        for cid in expired:
            del self._store[cid]
            logger.info("Purged expired conversation context", extra={"conversation_id": cid})
        return len(expired)


# Process-wide default store (multiple conversations share this store)
_default_store: ConversationMemoryStore | None = None
_default_lock = threading.Lock()


def get_default_store(ttl_seconds: int | None = None) -> ConversationMemoryStore:
    global _default_store
    with _default_lock:
        if _default_store is None:
            _default_store = ConversationMemoryStore(
                ttl_seconds=ttl_seconds or DEFAULT_TTL_SECONDS
            )
        elif ttl_seconds is not None and ttl_seconds != _default_store.ttl_seconds:
            _default_store.set_ttl(ttl_seconds)
        return _default_store


def reset_default_store() -> None:
    """Test helper: drop process-wide store."""
    global _default_store
    with _default_lock:
        _default_store = None
