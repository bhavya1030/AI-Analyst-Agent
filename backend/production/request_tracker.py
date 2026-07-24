"""Request ID generation and in-flight request tracking."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.production.logging import clear_context, get_request_id, set_request_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_request_id() -> str:
    return uuid.uuid4().hex


@dataclass
class TrackedRequest:
    request_id: str
    path: str = ""
    method: str = ""
    started_at: str = field(default_factory=_utc_now_iso)
    started_perf: float = field(default_factory=time.perf_counter)
    ended_at: Optional[str] = None
    duration_seconds: float = 0.0
    status: str = "in_flight"  # in_flight | completed | failed
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "path": self.path,
            "method": self.method,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


class RequestTracker:
    """Track concurrent and recent API requests by request_id."""

    def __init__(self, max_completed: int = 500):
        self._lock = threading.RLock()
        self._in_flight: dict[str, TrackedRequest] = {}
        self._completed: list[TrackedRequest] = []
        self.max_completed = max_completed

    def start(
        self,
        *,
        request_id: str | None = None,
        path: str = "",
        method: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> TrackedRequest:
        rid = request_id or get_request_id() or new_request_id()
        set_request_id(rid)
        req = TrackedRequest(
            request_id=rid,
            path=path,
            method=method,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._in_flight[rid] = req
        return req

    def finish(
        self,
        request_id: str | None = None,
        *,
        error: str | None = None,
    ) -> Optional[TrackedRequest]:
        rid = request_id or get_request_id()
        with self._lock:
            req = self._in_flight.pop(rid, None)
            if not req:
                return None
            req.ended_at = _utc_now_iso()
            req.duration_seconds = round(time.perf_counter() - req.started_perf, 6)
            req.status = "failed" if error else "completed"
            req.error = error
            self._completed.append(req)
            if len(self._completed) > self.max_completed:
                self._completed = self._completed[-self.max_completed :]
            return req

    def get(self, request_id: str) -> Optional[TrackedRequest]:
        with self._lock:
            if request_id in self._in_flight:
                return self._in_flight[request_id]
            for r in reversed(self._completed):
                if r.request_id == request_id:
                    return r
        return None

    def in_flight_count(self) -> int:
        with self._lock:
            return len(self._in_flight)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "in_flight": len(self._in_flight),
                "completed": len(self._completed),
                "in_flight_ids": list(self._in_flight.keys())[:50],
                "recent": [r.to_dict() for r in self._completed[-20:]],
            }


_default_tracker: RequestTracker | None = None
_tracker_lock = threading.Lock()


def get_request_tracker() -> RequestTracker:
    global _default_tracker
    with _tracker_lock:
        if _default_tracker is None:
            _default_tracker = RequestTracker()
        return _default_tracker


def reset_request_tracker() -> None:
    global _default_tracker
    with _tracker_lock:
        _default_tracker = None
        clear_context()
