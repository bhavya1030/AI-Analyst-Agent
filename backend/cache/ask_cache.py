"""Ask-level response cache.

Skips Planner → EDA → Viz → Forecast for identical requests against the
same dataset content.

Cache key
---------
  dataset_fingerprint (SHA256 of file/content)
  + normalized question
  + primary intent
  + parameters hash (horizon, columns, etc.)

Invalidation
------------
When dataset content changes, the fingerprint changes → automatic miss.
``invalidate_dataset`` purges all ask (and stage) entries for a fingerprint.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.cache.analysis_cache import (
    KIND_ASK,
    AnalysisCache,
    get_analysis_cache,
)
from backend.cache.fingerprint import (
    compute_dataset_fingerprint,
    fingerprint_file,
    params_hash,
)
from backend.core.logger import get_logger
from backend.db import SessionLocal
from backend.utils.intent_classifier import classify_intents
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

# Process-local stats (also durable hit_count lives on analysis_cache rows)
_STATS_LOCK = threading.RLock()
_STATS = {
    "lookups": 0,
    "hits": 0,
    "misses": 0,
    "stores": 0,
    "invalidations": 0,
    "cold_ms_total": 0.0,
    "warm_ms_total": 0.0,
    "cold_count": 0,
    "warm_count": 0,
}


@dataclass
class AskCacheKeyParts:
    dataset_fingerprint: str
    normalized_question: str
    intent: str
    params: dict[str, Any] = field(default_factory=dict)

    def params_for_hash(self) -> dict[str, Any]:
        return {
            "q": self.normalized_question,
            "intent": self.intent,
            **(self.params or {}),
        }


def normalize_question(question: str) -> str:
    """Canonicalize question text for stable cache keys."""
    q = (question or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    # Drop trailing punctuation noise
    q = q.rstrip("?.! ")
    return q


def primary_intent(question: str, intents: list[str] | None = None) -> str:
    intents = intents or classify_intents(question)
    if not intents:
        return "eda"
    # Prefer non-eda intents when present
    for intent in intents:
        if intent and intent != "eda":
            return str(intent)
    return str(intents[0] or "eda")


def resolve_dataset_fingerprint(
    *,
    file_path: str | None = None,
    dataset_path: str | None = None,
    dataset_url: str | None = None,
    data: Any = None,
    topic: str | None = None,
) -> Optional[str]:
    """
    Best-effort content fingerprint without running the full graph.

    Prefer local files; fall back to DataFrame / remote ref identity.
    """
    for ref in (file_path, dataset_path):
        if ref and Path(str(ref)).expanduser().is_file():
            fp = fingerprint_file(ref)
            if fp:
                return fp

    if data is not None:
        return compute_dataset_fingerprint(data, dataset_url or file_path or dataset_path)

    if dataset_url:
        return compute_dataset_fingerprint(None, dataset_url)

    if topic:
        # Weak provisional identity only when no content is known yet
        return None

    return None


def build_ask_params(
    question: str,
    *,
    intent: str | None = None,
    file_path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from backend.config import settings

    nq = normalize_question(question)
    intent_key = intent or primary_intent(question)
    params: dict[str, Any] = {
        "q": nq,
        "intent": intent_key,
        "horizon": int(getattr(settings, "FORECAST_HORIZON", 10)),
    }
    if file_path:
        # Path basename only — content is in fingerprint
        params["file"] = Path(str(file_path)).name.lower()
    if extra:
        for k, v in extra.items():
            if v is not None:
                params[str(k)] = v
    return params


def _record_lookup(hit: bool, elapsed_ms: float) -> None:
    with _STATS_LOCK:
        _STATS["lookups"] += 1
        if hit:
            _STATS["hits"] += 1
            _STATS["warm_ms_total"] += elapsed_ms
            _STATS["warm_count"] += 1
        else:
            _STATS["misses"] += 1


def _record_store(cold_ms: float | None = None) -> None:
    with _STATS_LOCK:
        _STATS["stores"] += 1
        if cold_ms is not None:
            _STATS["cold_ms_total"] += cold_ms
            _STATS["cold_count"] += 1


class AskCacheService:
    """Full-response cache for identical analytical asks."""

    def __init__(self) -> None:
        self._cache = get_analysis_cache()

    def get(
        self,
        fingerprint: str,
        question: str,
        *,
        intent: str | None = None,
        file_path: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
        """
        Lookup ask cache.

        Returns (payload_or_None, meta) where meta includes timing and hit flag.
        """
        t0 = time.perf_counter()
        if not fingerprint:
            elapsed = (time.perf_counter() - t0) * 1000
            _record_lookup(False, elapsed)
            return None, {
                "cache_hit": False,
                "reason": "no_fingerprint",
                "lookup_ms": round(elapsed, 2),
            }

        params = build_ask_params(
            question, intent=intent, file_path=file_path, extra=extra_params
        )
        payload = self._cache.get(KIND_ASK, fingerprint, params)
        elapsed = (time.perf_counter() - t0) * 1000
        hit = payload is not None and isinstance(payload, dict)
        _record_lookup(hit, elapsed)

        if hit:
            logger.info(
                "Ask cache HIT",
                extra={
                    "fingerprint": fingerprint[:16],
                    "intent": params.get("intent"),
                    "lookup_ms": round(elapsed, 2),
                    "q": params.get("q", "")[:80],
                },
            )
            # Shallow copy so callers can annotate without mutating L1
            body = dict(payload)
            body["cache_hit"] = True
            body["cache_kind"] = KIND_ASK
            body["dataset_fingerprint"] = fingerprint
            cold_ms = payload.get("_cold_ms")
            try:
                cold_ms_f = float(cold_ms) if cold_ms is not None else None
            except Exception:
                cold_ms_f = None
            saved = None
            if cold_ms_f is not None:
                saved = max(0.0, cold_ms_f - elapsed)
            return body, {
                "cache_hit": True,
                "lookup_ms": round(elapsed, 2),
                "cache_latency_ms": round(elapsed, 2),
                "cold_ms": cold_ms_f,
                "saved_time_ms": round(saved, 2) if saved is not None else None,
                "fingerprint": fingerprint,
                "intent": params.get("intent"),
                "params_hash": params_hash(params),
            }

        logger.info(
            "Ask cache MISS",
            extra={
                "fingerprint": fingerprint[:16],
                "intent": params.get("intent"),
                "lookup_ms": round(elapsed, 2),
                "q": params.get("q", "")[:80],
            },
        )
        return None, {
            "cache_hit": False,
            "reason": "miss",
            "lookup_ms": round(elapsed, 2),
            "fingerprint": fingerprint,
            "intent": params.get("intent"),
            "params_hash": params_hash(params),
        }

    def put(
        self,
        fingerprint: str,
        question: str,
        response: dict[str, Any],
        *,
        intent: str | None = None,
        file_path: str | None = None,
        extra_params: dict[str, Any] | None = None,
        cold_ms: float | None = None,
    ) -> Optional[str]:
        """Store final analytical response for this ask key."""
        if not fingerprint or not isinstance(response, dict):
            return None

        # Do not cache hard failures / acquisition prompts
        if response.get("needs_user_data") and not response.get("answer"):
            return None
        if response.get("error") and not response.get("answer") and not response.get("charts"):
            return None

        params = build_ask_params(
            question, intent=intent, file_path=file_path, extra=extra_params
        )
        store_body = _extract_cacheable_response(response)
        store_body["dataset_fingerprint"] = fingerprint
        store_body["cached_question"] = normalize_question(question)
        store_body["cached_intent"] = params.get("intent")
        if cold_ms is not None:
            store_body["_cold_ms"] = float(cold_ms)
        # Session delta: fields needed to refresh session without re-running graph
        store_body["session_delta"] = {
            "dataset_topic": response.get("dataset_topic") or "",
            "dataset_name": response.get("dataset_name") or "",
            "dataset_url": response.get("dataset_url") or "",
            "last_intent": response.get("last_intent") or params.get("intent"),
            "last_operation": response.get("last_operation"),
            "last_chart_type": response.get("last_chart_type"),
            "last_forecast_target": response.get("last_forecast_target"),
            "last_columns_used": response.get("last_columns_used")
            or response.get("columns")
            or [],
            "columns": response.get("columns") or [],
            "rows": response.get("rows") or 0,
            "dataset_fingerprint": fingerprint,
        }

        key = self._cache.put(KIND_ASK, fingerprint, store_body, params)
        _record_store(cold_ms)
        logger.info(
            "Ask cache STORE",
            extra={
                "fingerprint": fingerprint[:16],
                "intent": params.get("intent"),
                "cache_key": key,
                "cold_ms": cold_ms,
            },
        )
        return key

    def invalidate_dataset(self, fingerprint: str) -> int:
        """Purge all analysis_cache rows for a dataset fingerprint (all kinds)."""
        if not fingerprint:
            return 0
        n = self._cache.invalidate_fingerprint(fingerprint)
        with _STATS_LOCK:
            _STATS["invalidations"] += 1
        logger.info(
            "Ask cache invalidate dataset",
            extra={"fingerprint": fingerprint[:16], "deleted": n},
        )
        return n

    def stats(self) -> dict[str, Any]:
        """Process + durable cache statistics."""
        with _STATS_LOCK:
            lookups = int(_STATS["lookups"])
            hits = int(_STATS["hits"])
            misses = int(_STATS["misses"])
            stores = int(_STATS["stores"])
            inv = int(_STATS["invalidations"])
            cold_n = int(_STATS["cold_count"])
            warm_n = int(_STATS["warm_count"])
            cold_ms = float(_STATS["cold_ms_total"])
            warm_ms = float(_STATS["warm_ms_total"])

        hit_ratio = (hits / lookups) if lookups else 0.0
        durable = _durable_kind_stats()
        return {
            "lookups": lookups,
            "hits": hits,
            "misses": misses,
            "stores": stores,
            "invalidations": inv,
            "hit_ratio": round(hit_ratio, 4),
            "hit_ratio_pct": round(hit_ratio * 100, 2),
            "avg_cold_ms": round(cold_ms / cold_n, 2) if cold_n else None,
            "avg_warm_ms": round(warm_ms / warm_n, 2) if warm_n else None,
            "cold_count": cold_n,
            "warm_count": warm_n,
            "durable": durable,
            "target_hit_ratio_pct": 80.0,
            "target_warm_ms": 2000.0,
            "target_met": hit_ratio >= 0.80 if lookups >= 2 else None,
            "warm_under_2s": (
                (warm_ms / warm_n) < 2000.0 if warm_n else None
            ),
        }


def _extract_cacheable_response(response: dict[str, Any]) -> dict[str, Any]:
    """Persist final user-facing analysis artifacts only (no DataFrames).

    Already-sanitized payloads are stored once so warm hits avoid re-walking
    large Plotly trees.
    """
    charts = response.get("charts") or response.get("generated_charts") or []
    if not charts and response.get("chart"):
        charts = [response.get("chart")]

    # Prefer slim chart payloads when full figure is huge (keep structure)
    slim_charts = _slim_charts(charts)

    payload = {
        "answer": response.get("answer") or "",
        "dataset_summary": response.get("dataset_summary") or response.get("dataset_profile") or {},
        "dataset_topic": response.get("dataset_topic") or "",
        "dataset_name": response.get("dataset_name") or "",
        "charts": slim_charts,
        "generated_charts": slim_charts,
        "chart": response.get("chart") if not slim_charts else (slim_charts[0] if slim_charts else {}),
        "chart_columns_used": response.get("chart_columns_used") or [],
        "forecast": response.get("forecast") or [],
        "forecast_chart": response.get("forecast_chart") or {},
        "forecast_error": response.get("forecast_error") or "",
        "forecast_model": response.get("forecast_model") or "",
        "chart_error": response.get("chart_error") or "",
        "detected_patterns": response.get("detected_patterns") or [],
        "insights": response.get("insights") or [],
        "recommended_next_steps": response.get("recommended_next_steps") or [],
        "dataset_explanation": response.get("dataset_explanation") or [],
        "related_datasets": response.get("related_datasets") or [],
        "chart_explanation": response.get("chart_explanation") or "",
        "hypotheses": response.get("hypotheses") or [],
        "dataset_url": response.get("dataset_url") or "",
        "rows": response.get("rows") or 0,
        "columns": response.get("columns") or [],
        "error": response.get("error") or "",
        "error_type": response.get("error_type") or "",
        "needs_user_data": bool(response.get("needs_user_data")),
        "data_acquisition_options": response.get("data_acquisition_options") or [],
        "dataset_discovery": response.get("dataset_discovery") or {},
        "search_queries": response.get("search_queries") or [],
        "source": response.get("source") or response.get("dataset_source") or "",
        "product_promise": response.get("product_promise") or "",
        "last_intent": response.get("last_intent"),
        "last_operation": response.get("last_operation"),
        "last_chart_type": response.get("last_chart_type"),
        "last_forecast_target": response.get("last_forecast_target"),
        "last_columns_used": response.get("last_columns_used") or response.get("columns") or [],
        # EDA / artifacts bundle
        "eda": {
            "dataset_profile": response.get("dataset_summary")
            or response.get("dataset_profile")
            or {},
            "detected_patterns": response.get("detected_patterns") or [],
            "insights": response.get("insights") or [],
        },
        "artifacts": {
            "charts": slim_charts,
            "forecast": response.get("forecast") or [],
            "forecast_chart": response.get("forecast_chart") or {},
            "hypotheses": response.get("hypotheses") or [],
            "recommended_next_steps": response.get("recommended_next_steps") or [],
        },
        "_sanitized": True,
    }
    # Single sanitize at store time (warm path must not re-sanitize)
    return sanitize_for_json(payload)


def _slim_charts(charts: Any) -> list[Any]:
    """Keep chart payloads usable but avoid multi-MB binary embeds when possible."""
    if not charts:
        return []
    if not isinstance(charts, list):
        charts = [charts]
    out: list[Any] = []
    for ch in charts[:8]:
        if not isinstance(ch, dict):
            out.append(ch)
            continue
        # Drop heavy base64 image blobs if present (keep plotly data/layout)
        slim = {k: v for k, v in ch.items() if k not in {"image_base64", "png", "thumbnail"}}
        fig = slim.get("figure") or slim.get("plotly")
        if isinstance(fig, dict) and "data" in fig:
            # Keep figure structure as-is — already JSON-serializable after sanitize
            pass
        out.append(slim)
    return out


def _durable_kind_stats() -> dict[str, Any]:
    db = SessionLocal()
    try:
        rows = (
            db.query(
                AnalysisCache.kind,
                AnalysisCache.hit_count,
            )
            .all()
        )
        by_kind: dict[str, dict[str, int]] = {}
        total_rows = 0
        total_hits = 0
        ask_rows = 0
        ask_hits = 0
        for kind, hit_count in rows:
            total_rows += 1
            hc = int(hit_count or 0)
            total_hits += hc
            k = str(kind or "unknown")
            slot = by_kind.setdefault(k, {"rows": 0, "hit_count_sum": 0})
            slot["rows"] += 1
            slot["hit_count_sum"] += hc
            if k == KIND_ASK:
                ask_rows += 1
                ask_hits += hc
        return {
            "rows": total_rows,
            "hit_count_sum": total_hits,
            "by_kind": by_kind,
            "ask_rows": ask_rows,
            "ask_hit_count_sum": ask_hits,
            "ask_entry_hit_ratio": round(ask_hits / ask_rows, 4) if ask_rows else 0.0,
        }
    except Exception as exc:
        logger.warning("Durable cache stats failed", extra={"error": str(exc)})
        return {"error": str(exc)}
    finally:
        db.close()


_ask_service: AskCacheService | None = None
_ask_lock = threading.Lock()


def get_ask_cache() -> AskCacheService:
    global _ask_service
    with _ask_lock:
        if _ask_service is None:
            _ask_service = AskCacheService()
        return _ask_service


def reset_ask_cache_stats() -> None:
    """Test helper — clear process-local counters."""
    with _STATS_LOCK:
        for k in list(_STATS.keys()):
            _STATS[k] = 0 if not str(k).endswith("_ms_total") else 0.0
