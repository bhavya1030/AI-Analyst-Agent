"""Execution tracing with spans and request correlation."""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from backend.production.logging import get_request_id, get_trace_id, set_request_id, set_trace_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Span:
    name: str
    span_id: str
    trace_id: str
    parent_id: Optional[str] = None
    started_at: str = field(default_factory=_utc_now_iso)
    ended_at: Optional[str] = None
    duration_seconds: float = 0.0
    status: str = "ok"  # ok | error
    attributes: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Trace:
    trace_id: str
    request_id: str
    started_at: str = field(default_factory=_utc_now_iso)
    ended_at: Optional[str] = None
    spans: list[Span] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "spans": [s.to_dict() for s in self.spans],
            "attributes": dict(self.attributes),
            "n_spans": len(self.spans),
        }


class Tracer:
    """In-memory tracer for recent requests (bounded ring buffer)."""

    def __init__(self, max_traces: int = 200):
        self._lock = threading.RLock()
        self._traces: dict[str, Trace] = {}
        self._order: list[str] = []
        self.max_traces = max_traces
        self._active_span: dict[str, str] = {}  # trace_id → current span_id

    def start_trace(
        self,
        *,
        request_id: str | None = None,
        trace_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Trace:
        rid = request_id or get_request_id() or uuid.uuid4().hex
        tid = trace_id or get_trace_id() or uuid.uuid4().hex
        set_request_id(rid)
        set_trace_id(tid)
        trace = Trace(trace_id=tid, request_id=rid, attributes=dict(attributes or {}))
        with self._lock:
            self._traces[tid] = trace
            self._order.append(tid)
            self._trim()
        return trace

    def end_trace(self, trace_id: str | None = None) -> Optional[Trace]:
        tid = trace_id or get_trace_id()
        with self._lock:
            trace = self._traces.get(tid)
            if not trace:
                return None
            trace.ended_at = _utc_now_iso()
            return trace

    @contextmanager
    def span(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Span, None, None]:
        tid = trace_id or get_trace_id()
        if not tid:
            # auto-start a trace
            tr = self.start_trace()
            tid = tr.trace_id

        span_id = uuid.uuid4().hex[:16]
        with self._lock:
            parent = self._active_span.get(tid)
            self._active_span[tid] = span_id
            span = Span(
                name=name,
                span_id=span_id,
                trace_id=tid,
                parent_id=parent,
                attributes=dict(attributes or {}),
            )
            if tid in self._traces:
                self._traces[tid].spans.append(span)

        t0 = time.perf_counter()
        try:
            yield span
            span.status = "ok"
        except Exception as exc:
            span.status = "error"
            span.error = str(exc)
            raise
        finally:
            span.duration_seconds = round(time.perf_counter() - t0, 6)
            span.ended_at = _utc_now_iso()
            with self._lock:
                if self._active_span.get(tid) == span_id:
                    if parent:
                        self._active_span[tid] = parent
                    else:
                        self._active_span.pop(tid, None)

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        with self._lock:
            return self._traces.get(trace_id)

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(reversed(self._order))[:limit]
            return [self._traces[i].to_dict() for i in ids if i in self._traces]

    def _trim(self) -> None:
        while len(self._order) > self.max_traces:
            old = self._order.pop(0)
            self._traces.pop(old, None)
            self._active_span.pop(old, None)


_default_tracer: Tracer | None = None
_tracer_lock = threading.Lock()


def get_tracer() -> Tracer:
    global _default_tracer
    with _tracer_lock:
        if _default_tracer is None:
            _default_tracer = Tracer()
        return _default_tracer


def reset_tracer() -> None:
    global _default_tracer
    with _tracer_lock:
        _default_tracer = None


def trace_request(
    name: str = "request",
    *,
    request_id: str | None = None,
    attributes: dict[str, Any] | None = None,
):
    """
    Context manager: start request trace + root span.

    Usage:
        with trace_request("api.chat", attributes={"path": "/chat"}) as ctx:
            ...
            ctx["trace_id"]
    """

    @contextmanager
    def _cm():
        tracer = get_tracer()
        trace = tracer.start_trace(request_id=request_id, attributes=attributes)
        with tracer.span(name, attributes=attributes) as span:
            yield {
                "trace_id": trace.trace_id,
                "request_id": trace.request_id,
                "span": span,
                "tracer": tracer,
            }
        tracer.end_trace(trace.trace_id)

    return _cm()
