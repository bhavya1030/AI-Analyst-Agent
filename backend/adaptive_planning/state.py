"""In-memory store for adaptive execution plans (multi-plan safe)."""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Optional

from backend.adaptive_planning.models import AdaptiveExecutionPlan, PlanStatus
from backend.core.logger import get_logger

logger = get_logger(__name__)


class AdaptivePlanStore:
    """
    Thread-safe store of AdaptiveExecutionPlan instances keyed by plan_id.

    Does not persist to disk — process-local only (fine for adaptive control loop).
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._plans: dict[str, AdaptiveExecutionPlan] = {}

    def put(self, plan: AdaptiveExecutionPlan) -> AdaptiveExecutionPlan:
        if not plan or not plan.plan_id:
            raise ValueError("plan.plan_id is required")
        with self._lock:
            plan.sync_state()
            self._plans[plan.plan_id] = deepcopy(plan)
            return deepcopy(self._plans[plan.plan_id])

    def get(self, plan_id: str) -> Optional[AdaptiveExecutionPlan]:
        with self._lock:
            plan = self._plans.get((plan_id or "").strip())
            return deepcopy(plan) if plan else None

    def delete(self, plan_id: str) -> bool:
        with self._lock:
            return self._plans.pop((plan_id or "").strip(), None) is not None

    def list_ids(self, *, status: PlanStatus | None = None) -> list[str]:
        with self._lock:
            if status is None:
                return list(self._plans.keys())
            return [
                pid
                for pid, p in self._plans.items()
                if p.status == status
            ]

    def clear(self) -> int:
        with self._lock:
            n = len(self._plans)
            self._plans.clear()
            return n

    def count(self) -> int:
        with self._lock:
            return len(self._plans)


_default_store: AdaptivePlanStore | None = None
_store_lock = threading.Lock()


def get_default_store() -> AdaptivePlanStore:
    global _default_store
    with _store_lock:
        if _default_store is None:
            _default_store = AdaptivePlanStore()
        return _default_store


def reset_default_store() -> None:
    global _default_store
    with _store_lock:
        if _default_store is not None:
            _default_store.clear()
        _default_store = None
