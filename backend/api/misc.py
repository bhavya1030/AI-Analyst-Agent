"""Miscellaneous routes — home, learned-datasets, cache, metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.auth.context import AuthUser
from backend.auth.deps import get_current_user
from backend.utils.json_safe import sanitize_for_json

router = APIRouter(tags=["misc"])


@router.get("/")
def home():
    return {"message": "AI Analyst Backend Running"}


@router.get("/v1/learned-datasets")
@router.get("/learned-datasets")
def learned_datasets(limit: int = 50):
    """List datasets the copilot has remembered from successful loads."""
    try:
        from backend.memory.learned_datasets import list_learned_datasets

        return sanitize_for_json({"learned_datasets": list_learned_datasets(limit=limit)})
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "Could not list learned datasets", "details": str(exc)},
        )


@router.get("/v1/cache/stats")
@router.get("/cache/stats")
def cache_stats(user: AuthUser = Depends(get_current_user)):
    """Ask-level + durable analysis cache statistics."""
    from backend.cache.ask_cache import get_ask_cache

    try:
        stats = get_ask_cache().stats()
        stats["user_id"] = user.user_id
        return sanitize_for_json(stats)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "Unable to read cache stats", "details": str(exc)},
        )


@router.post("/v1/cache/invalidate")
@router.post("/cache/invalidate")
def cache_invalidate(
    fingerprint: str | None = None,
    file_path: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """Invalidate cache entries when a dataset changes."""
    from backend.cache.ask_cache import get_ask_cache, resolve_dataset_fingerprint

    fp = (fingerprint or "").strip()
    if not fp and file_path:
        fp = resolve_dataset_fingerprint(file_path=file_path) or ""
    if not fp:
        return JSONResponse(
            status_code=400,
            content={"error": "fingerprint or file_path is required"},
        )
    deleted = get_ask_cache().invalidate_dataset(fp)
    return sanitize_for_json(
        {
            "fingerprint": fp,
            "deleted": deleted,
            "user_id": user.user_id,
            "stats": get_ask_cache().stats(),
        }
    )


@router.get("/v1/metrics/timings")
@router.get("/metrics/timings")
def metrics_timings(user: AuthUser = Depends(get_current_user)):
    """Aggregate stage timing stats across process lifetime."""
    from backend.production.pipeline_timing import aggregate_timing_stats

    return sanitize_for_json(
        {"stages": aggregate_timing_stats(), "user_id": user.user_id}
    )
