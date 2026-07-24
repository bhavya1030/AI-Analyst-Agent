"""Health checks for core production dependencies."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend.production.config_validator import validate_config
from backend.production.logging import get_production_logger

logger = get_production_logger("backend.production.health")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ComponentHealth:
    name: str
    status: str  # up | down | degraded | skipped
    latency_ms: float = 0.0
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 3),
            "detail": self.detail,
            "metadata": dict(self.metadata),
        }


@dataclass
class HealthReport:
    status: str  # healthy | degraded | unhealthy
    checked_at: str = field(default_factory=_utc_now_iso)
    components: list[ComponentHealth] = field(default_factory=list)
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_at": self.checked_at,
            "version": self.version,
            "components": [c.to_dict() for c in self.components],
        }


def _time_check(name: str, fn: Callable[[], tuple[str, str, dict]]) -> ComponentHealth:
    t0 = time.perf_counter()
    try:
        status, detail, meta = fn()
        return ComponentHealth(
            name=name,
            status=status,
            latency_ms=(time.perf_counter() - t0) * 1000,
            detail=detail,
            metadata=meta,
        )
    except Exception as exc:
        return ComponentHealth(
            name=name,
            status="down",
            latency_ms=(time.perf_counter() - t0) * 1000,
            detail=str(exc),
        )


def check_registry() -> ComponentHealth:
    def _run():
        from backend.registry import DatasetRegistryService

        svc = DatasetRegistryService()
        # lightweight list / count
        try:
            items = svc.list_datasets() if hasattr(svc, "list_datasets") else []
            n = len(items) if items is not None else 0
        except Exception:
            # try repository path
            n = 0
            if hasattr(svc, "_repo") and hasattr(svc._repo, "list_all"):
                n = len(svc._repo.list_all() or [])
        return "up", f"{n} datasets registered", {"count": n}

    return _time_check("registry", _run)


def check_library() -> ComponentHealth:
    def _run():
        from backend.dataset_library import DatasetLibraryService, get_default_storage

        storage = get_default_storage()
        root = getattr(storage, "root", None) or getattr(storage, "base_path", None)
        exists = True
        if root is not None:
            exists = Path(root).exists()
        status = "up" if exists else "degraded"
        return status, f"library storage root={root}", {"exists": exists, "root": str(root)}

    return _time_check("library", _run)


def check_semantic_db() -> ComponentHealth:
    def _run():
        try:
            from backend.semantic import search_similar

            # Do not force model load if avoidable — just import surface
            return "up", "semantic module importable", {"search_similar": True}
        except Exception as exc:
            return "down", str(exc), {}

    return _time_check("semantic_db", _run)


def check_vector_db() -> ComponentHealth:
    def _run():
        try:
            from backend.semantic.vector_store import NumpyVectorStore

            store = NumpyVectorStore(dim=8)
            # tiny smoke
            import numpy as np

            store.add("t1", np.ones(8, dtype=float) / (8**0.5))
            hits = store.search(np.ones(8, dtype=float) / (8**0.5), top_k=1)
            ok = bool(hits)
            return ("up" if ok else "degraded"), "numpy vector store ok", {"backend": "numpy"}
        except Exception as exc:
            # FAISS optional
            return "degraded", f"vector store: {exc}", {}

    return _time_check("vector_db", _run)


def check_llm() -> ComponentHealth:
    def _run():
        try:
            from backend.startup.ollama_validator import get_ollama_status

            status = get_ollama_status()
            running = bool(status.get("ollama_running"))
            model_ok = bool(status.get("model_available"))
            if running and model_ok:
                return "up", f"model={status.get('model_name')}", status
            if running:
                return "degraded", "Ollama running but model unavailable", status
            return "degraded", "Ollama not running (rule-based fallback OK)", status
        except Exception as exc:
            return "degraded", f"LLM check failed: {exc}", {}

    return _time_check("llm", _run)


def check_storage() -> ComponentHealth:
    def _run():
        try:
            from backend.config import settings

            data_dir = Path(settings.DATA_DIR)
            data_dir.mkdir(parents=True, exist_ok=True)
            probe = data_dir / ".health_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return "up", f"writable {data_dir}", {"path": str(data_dir)}
        except Exception as exc:
            return "down", str(exc), {}

    return _time_check("storage", _run)


def health(*, deep: bool = False) -> dict[str, Any]:
    """
    Aggregate health check.

    Components: Registry, Library, Semantic DB, LLM, Vector DB, Storage
    """
    components = [
        check_registry(),
        check_library(),
        check_semantic_db(),
        check_vector_db(),
        check_llm(),
        check_storage(),
    ]

    if deep:
        cfg = validate_config()
        components.append(
            ComponentHealth(
                name="config",
                status="up" if cfg.ok else "degraded",
                detail="config ok" if cfg.ok else f"{len(cfg.errors)} config error(s)",
                metadata=cfg.to_dict(),
            )
        )

    statuses = [c.status for c in components]
    if any(s == "down" for s in statuses):
        overall = "unhealthy"
    elif any(s == "degraded" for s in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    report = HealthReport(status=overall, components=components)
    return report.to_dict()
