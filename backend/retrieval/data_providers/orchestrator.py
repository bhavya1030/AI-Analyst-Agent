"""Provider orchestrator v2 — topic/country/metric routing → search → validate → retry."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from backend.core.logger import get_logger
from backend.retrieval.data_providers.base import (
    DataProvider,
    DatasetCandidate,
    ProviderSearchResult,
)
from backend.retrieval.data_providers.csv_url import CsvUrlProvider
from backend.retrieval.data_providers.data_gov import DataGovProvider
from backend.retrieval.data_providers.eurostat import EurostatProvider
from backend.retrieval.data_providers.fred import FredProvider
from backend.retrieval.data_providers.github_raw import GitHubRawProvider
from backend.retrieval.data_providers.huggingface import HuggingFaceProvider
from backend.retrieval.data_providers.json_api import JsonApiProvider
from backend.retrieval.data_providers.kaggle import KaggleProvider
from backend.retrieval.data_providers.owid import OWIDProvider
from backend.retrieval.data_providers.topic import TopicContext, extract_topic_context
from backend.retrieval.data_providers.validation import (
    is_blocked_url,
    looks_like_file_url,
    probe_download,
    validate_url_metadata,
)
from backend.retrieval.data_providers.world_bank import WorldBankProvider

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class OrchestratorResult:
    success: bool
    candidate: Optional[DatasetCandidate] = None
    validation: Optional[dict[str, Any]] = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    providers_tried: list[str] = field(default_factory=list)
    retry_count: int = 0
    failure_reason: str = ""
    graceful_message: str = ""
    topic: str = ""
    keywords: list[str] = field(default_factory=list)
    country: list[str] = field(default_factory=list)
    metric: Optional[str] = None
    time_period: Optional[str] = None
    domain: str = "general"
    provenance: dict[str, Any] = field(default_factory=dict)
    total_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "candidate": self.candidate.to_metadata() if self.candidate else None,
            "validation": self.validation,
            "attempts": self.attempts,
            "providers_tried": self.providers_tried,
            "retry_count": self.retry_count,
            "failure_reason": self.failure_reason,
            "graceful_message": self.graceful_message,
            "topic": self.topic,
            "keywords": self.keywords,
            "country": self.country,
            "metric": self.metric,
            "time_period": self.time_period,
            "domain": self.domain,
            "provenance": self.provenance,
            "total_ms": self.total_ms,
        }


def default_providers() -> list[DataProvider]:
    """Ordered default stack (selection re-ranks at runtime)."""
    return [
        CsvUrlProvider(),
        OWIDProvider(),
        WorldBankProvider(),
        FredProvider(),
        EurostatProvider(),
        GitHubRawProvider(),
        JsonApiProvider(),
        DataGovProvider(),
        HuggingFaceProvider(),
        KaggleProvider(),
    ]


class ProviderOrchestrator:
    """
    Production retrieval orchestrator v2.

    Flow:
      topic → {country, metric, time, domain}
      → order providers by affinity
      → Provider A search → validate
      → fail → Provider B → Provider C …
      → success (with provenance) or graceful message
    """

    def __init__(
        self,
        providers: Sequence[DataProvider] | None = None,
        *,
        validate: bool = True,
        max_candidates_per_provider: int = 5,
        max_attempts: int = 16,
    ):
        self.providers = list(providers) if providers is not None else default_providers()
        self.validate = validate
        self.max_candidates_per_provider = max_candidates_per_provider
        self.max_attempts = max_attempts

    def resolve(self, topic: str) -> OrchestratorResult:
        t0 = time.perf_counter()
        ctx = extract_topic_context(topic)
        ordered = self._order_providers(ctx)

        logger.info(
            "Provider orchestrator v2 start",
            extra={
                "topic": ctx.normalized,
                "keywords": ctx.keywords[:12],
                "aliases": ctx.aliases,
                "country": ctx.country,
                "metric": ctx.metric,
                "domain": ctx.domain,
                "providers": [p.name for p in ordered],
            },
        )

        attempts: list[dict[str, Any]] = []
        providers_tried: list[str] = []
        retries = 0
        last_failure = "No downloadable dataset candidates found."

        for provider in ordered:
            providers_tried.append(provider.name)
            search_t0 = time.perf_counter()
            try:
                candidates = provider.search(
                    ctx.raw or ctx.normalized,
                    ctx.keywords,
                    limit=self.max_candidates_per_provider,
                ) or []
                # Enrich candidates with context defaults
                for c in candidates:
                    if not c.country and ctx.country:
                        c.country = list(ctx.country)
                    if not c.metric and ctx.metric:
                        c.metric = ctx.metric
                    if not c.time_period and ctx.time_period:
                        c.time_period = ctx.time_period
                    if c.confidence <= 0:
                        c.confidence = 0.5
                # Prefer higher confidence / rank
                candidates = sorted(
                    candidates,
                    key=lambda c: (c.confidence, c.rank),
                    reverse=True,
                )
                search_ms = (time.perf_counter() - search_t0) * 1000
            except Exception as exc:
                search_ms = (time.perf_counter() - search_t0) * 1000
                last_failure = f"{provider.name}:search_error:{exc}"
                attempts.append(
                    {
                        "provider": provider.name,
                        "stage": "search",
                        "ok": False,
                        "error": str(exc),
                        "duration_ms": round(search_ms, 1),
                    }
                )
                logger.warning(
                    "Provider search failed — trying next",
                    extra={"provider": provider.name, "error": str(exc)},
                )
                retries += 1
                continue

            logger.info(
                "Provider search complete",
                extra={
                    "provider": provider.name,
                    "candidates": len(candidates),
                    "duration_ms": round(search_ms, 1),
                },
            )

            if not candidates:
                attempts.append(
                    {
                        "provider": provider.name,
                        "stage": "search",
                        "ok": False,
                        "error": "no_candidates",
                        "duration_ms": round(search_ms, 1),
                    }
                )
                retries += 1
                continue

            for cand in candidates:
                if retries >= self.max_attempts:
                    break
                if not cand.download_url or cand.extra.get("metadata_only"):
                    last_failure = f"{provider.name}:metadata_only_or_empty_url"
                    attempts.append(
                        {
                            "provider": provider.name,
                            "stage": "candidate",
                            "ok": False,
                            "error": last_failure,
                            "title": cand.title,
                        }
                    )
                    retries += 1
                    continue

                blocked, why = is_blocked_url(cand.download_url)
                if blocked:
                    last_failure = f"{provider.name}:blocked_url:{why}"
                    attempts.append(
                        {
                            "provider": provider.name,
                            "stage": "url_block",
                            "ok": False,
                            "error": last_failure,
                            "url": cand.download_url,
                        }
                    )
                    logger.info(
                        "Candidate rejected (blocked URL)",
                        extra={
                            "provider": provider.name,
                            "url": cand.download_url,
                            "reason": why,
                        },
                    )
                    retries += 1
                    continue

                if not self.validate:
                    total_ms = (time.perf_counter() - t0) * 1000
                    prov = self._build_provenance(cand, validation=None, ctx=ctx)
                    return OrchestratorResult(
                        success=True,
                        candidate=cand,
                        validation={"ok": True, "reason": "validation_skipped"},
                        attempts=attempts,
                        providers_tried=providers_tried,
                        retry_count=retries,
                        topic=ctx.normalized,
                        keywords=ctx.keywords,
                        country=list(ctx.country),
                        metric=ctx.metric,
                        time_period=ctx.time_period,
                        domain=ctx.domain,
                        provenance=prov,
                        total_ms=round(total_ms, 1),
                    )

                val_t0 = time.perf_counter()
                if looks_like_file_url(cand.download_url) or cand.file_format in {
                    "csv", "json", "xlsx", "parquet", "zip", "xls",
                }:
                    v = probe_download(cand.download_url)
                else:
                    v = validate_url_metadata(cand.download_url)
                    if v.ok:
                        v = probe_download(cand.download_url)
                val_ms = (time.perf_counter() - val_t0) * 1000

                attempt = {
                    "provider": provider.name,
                    "stage": "validate",
                    "ok": v.ok,
                    "error": None if v.ok else v.reason,
                    "url": cand.download_url,
                    "final_url": v.final_url,
                    "duration_ms": round(val_ms, 1),
                    "file_format": v.file_format,
                    "content_type": v.content_type,
                    "status_code": v.status_code,
                    "confidence": cand.confidence,
                }
                attempts.append(attempt)

                logger.info(
                    "Candidate validation",
                    extra={
                        "provider": provider.name,
                        "ok": v.ok,
                        "reason": v.reason,
                        "url": cand.download_url,
                        "duration_ms": round(val_ms, 1),
                        "retry_count": retries,
                    },
                )

                if not v.ok:
                    last_failure = f"{provider.name}:validation:{v.reason}"
                    retries += 1
                    continue

                # Success — attach format + final URL + provenance
                if v.file_format:
                    cand.file_format = v.file_format
                if v.final_url and v.final_url != cand.download_url:
                    cand.source_url = cand.source_url or cand.download_url
                    cand.download_url = v.final_url

                content_hash = None
                if v.content:
                    content_hash = hashlib.sha256(v.content[: 512 * 1024]).hexdigest()
                    if v.size_bytes and v.size_bytes > 512 * 1024:
                        content_hash = f"partial:{content_hash}"

                prov = self._build_provenance(
                    cand, validation=v.to_dict(), ctx=ctx, content_hash=content_hash
                )
                # Fold provenance into candidate extra for registry learning
                cand.extra = {
                    **(cand.extra or {}),
                    "hash": content_hash,
                    "content_hash": content_hash,
                    "download_date": _utc_now_iso()[:10],
                    "provenance": prov,
                }

                total_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "Provider orchestrator success",
                    extra={
                        "provider": provider.name,
                        "title": cand.title,
                        "url": cand.download_url,
                        "confidence": cand.confidence,
                        "retry_count": retries,
                        "total_ms": round(total_ms, 1),
                    },
                )
                return OrchestratorResult(
                    success=True,
                    candidate=cand,
                    validation=v.to_dict(),
                    attempts=attempts,
                    providers_tried=providers_tried,
                    retry_count=retries,
                    topic=ctx.normalized,
                    keywords=ctx.keywords,
                    country=list(ctx.country),
                    metric=ctx.metric,
                    time_period=ctx.time_period,
                    domain=ctx.domain,
                    provenance=prov,
                    total_ms=round(total_ms, 1),
                )

            retries += 1

        total_ms = (time.perf_counter() - t0) * 1000
        graceful = self._graceful_message(ctx, providers_tried, last_failure)
        logger.warning(
            "Provider orchestrator exhausted",
            extra={
                "topic": ctx.normalized,
                "retry_count": retries,
                "providers_tried": providers_tried,
                "failure_reason": last_failure,
                "total_ms": round(total_ms, 1),
            },
        )
        return OrchestratorResult(
            success=False,
            candidate=None,
            validation=None,
            attempts=attempts,
            providers_tried=providers_tried,
            retry_count=retries,
            failure_reason=last_failure,
            graceful_message=graceful,
            topic=ctx.normalized,
            keywords=ctx.keywords,
            country=list(ctx.country),
            metric=ctx.metric,
            time_period=ctx.time_period,
            domain=ctx.domain,
            total_ms=round(total_ms, 1),
        )

    def _order_providers(self, ctx: TopicContext) -> list[DataProvider]:
        scored: list[tuple[int, DataProvider]] = []
        for p in self.providers:
            if hasattr(p, "score_for_context"):
                score = p.score_for_context(
                    ctx.normalized,
                    ctx.keywords,
                    country=ctx.country,
                    metric=ctx.metric,
                    time_period=ctx.time_period,
                    domain=ctx.domain,
                    aliases=ctx.aliases,
                )
            else:
                score = p.preferred_for(ctx.normalized, ctx.keywords)

            # Always keep high-coverage fallbacks
            if score < 0 and p.name in {"csv_url", "github_raw", "data_gov", "world_bank"}:
                score = max(10, p.priority // 2)
            if score < 0 and p.name == "kaggle":
                continue
            if score < 0:
                score = max(0, p.priority // 4)
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    @staticmethod
    def _build_provenance(
        cand: DatasetCandidate,
        *,
        validation: dict | None,
        ctx: TopicContext,
        content_hash: str | None = None,
    ) -> dict[str, Any]:
        return {
            "provider": cand.provider,
            "version": cand.dataset_version,
            "dataset_version": cand.dataset_version,
            "download_date": _utc_now_iso()[:10],
            "download_timestamp": _utc_now_iso(),
            "license": cand.license,
            "hash": content_hash,
            "content_hash": content_hash,
            "download_url": cand.download_url,
            "source_url": cand.source_url or cand.download_url,
            "confidence": cand.confidence,
            "metric": cand.metric or ctx.metric,
            "country": cand.country or list(ctx.country),
            "time_period": cand.time_period or ctx.time_period,
            "domain": ctx.domain,
            "validation": validation,
        }

    @staticmethod
    def _graceful_message(
        ctx: TopicContext, providers_tried: list[str], last_failure: str
    ) -> str:
        topic = ctx.raw or ctx.normalized or "this topic"
        tried = ", ".join(providers_tried) if providers_tried else "no providers"
        return (
            f'Could not find a validated downloadable dataset for "{topic}". '
            f"Tried providers: {tried}. "
            f"Last error: {last_failure}. "
            "Upload a CSV/JSON file, paste a direct file URL, or rephrase the topic."
        )


_default_orchestrator: ProviderOrchestrator | None = None


def get_provider_orchestrator() -> ProviderOrchestrator:
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = ProviderOrchestrator()
    return _default_orchestrator


def set_provider_orchestrator(orch: ProviderOrchestrator | None) -> None:
    global _default_orchestrator
    _default_orchestrator = orch
