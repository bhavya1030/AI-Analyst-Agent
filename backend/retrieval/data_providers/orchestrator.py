"""Provider orchestrator v3 — parallel search, budgets, circuit breakers, ranking."""

from __future__ import annotations

import concurrent.futures
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from backend.config import settings
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
from backend.retrieval.data_providers.provider_circuit import (
    is_provider_available,
    provider_circuit_status,
    record_provider_failure,
    record_provider_success,
)
from backend.retrieval.data_providers.ranking import rank_candidates
from backend.retrieval.data_providers.timeout_budget import (
    BudgetSnapshot,
    is_retryable_error,
    new_budget,
    run_with_timeout,
)
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


def _max_parallel() -> int:
    return int(getattr(settings, "RETRIEVAL_MAX_PARALLEL_PROVIDERS", 8) or 8)


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
    # Retrieval v3 metrics
    metrics: dict[str, Any] = field(default_factory=dict)

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
            "metrics": self.metrics,
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
    Production retrieval orchestrator v3.

    Flow:
      topic → {country, metric, time, domain}
      → order providers by affinity; skip circuit-open
      → parallel search (ThreadPoolExecutor) with per-provider timeout
      → respect global retrieval budget
      → rank candidates (confidence · freshness · trust · schema · size)
      → validate top candidates within remaining budget
      → success with metrics / provenance or graceful message
    """

    def __init__(
        self,
        providers: Sequence[DataProvider] | None = None,
        *,
        validate: bool = True,
        max_candidates_per_provider: int = 5,
        max_attempts: int = 16,
        provider_timeout_s: float | None = None,
        global_budget_s: float | None = None,
        max_parallel: int | None = None,
    ):
        self.providers = list(providers) if providers is not None else default_providers()
        self.validate = validate
        self.max_candidates_per_provider = max_candidates_per_provider
        self.max_attempts = max_attempts
        self.provider_timeout_s = provider_timeout_s
        self.global_budget_s = global_budget_s
        self.max_parallel = max_parallel

    def resolve(self, topic: str) -> OrchestratorResult:
        budget = new_budget(
            provider_timeout_s=self.provider_timeout_s,
            global_budget_s=self.global_budget_s,
        )
        t0 = budget.started_at
        ctx = extract_topic_context(topic)
        ordered = self._order_providers(ctx)

        metrics: dict[str, Any] = {
            "provider_latency_ms": {},
            "provider_timeout": {},
            "provider_rank": {},
            "provider_success": {},
            "retrieval_budget_used": 0.0,
            "circuit_skipped": [],
            "parallel_workers": 0,
        }

        available: list[DataProvider] = []
        for p in ordered:
            if is_provider_available(p.name):
                available.append(p)
            else:
                metrics["circuit_skipped"].append(p.name)
                status = provider_circuit_status(p.name)
                logger.info(
                    "Provider skipped (circuit open)",
                    extra={
                        "provider": p.name,
                        "next_retry_in_s": status.get("next_retry_in_s"),
                        "failure_reason": status.get("failure_reason"),
                    },
                )

        logger.info(
            "Provider orchestrator v3 start",
            extra={
                "topic": ctx.normalized,
                "keywords": ctx.keywords[:12],
                "aliases": ctx.aliases,
                "country": ctx.country,
                "metric": ctx.metric,
                "domain": ctx.domain,
                "providers": [p.name for p in available],
                "circuit_skipped": metrics["circuit_skipped"],
                "provider_timeout_s": budget.provider_timeout_s,
                "global_budget_s": budget.global_budget_s,
            },
        )

        attempts: list[dict[str, Any]] = []
        providers_tried: list[str] = []
        retries = 0
        last_failure = "No downloadable dataset candidates found."

        # ── Parallel search phase ──────────────────────────────────────────
        search_results = self._parallel_search(
            available, ctx, budget, metrics, attempts, providers_tried
        )
        retries += sum(1 for a in attempts if a.get("stage") == "search" and not a.get("ok"))

        # Flatten + enrich candidates
        all_candidates: list[DatasetCandidate] = []
        for provider_name, candidates, search_ok, search_err in search_results:
            if not search_ok or not candidates:
                if search_err:
                    last_failure = f"{provider_name}:search_error:{search_err}"
                elif not candidates:
                    last_failure = f"{provider_name}:no_candidates"
                continue
            for c in candidates:
                if not c.country and ctx.country:
                    c.country = list(ctx.country)
                if not c.metric and ctx.metric:
                    c.metric = ctx.metric
                if not c.time_period and ctx.time_period:
                    c.time_period = ctx.time_period
                if c.confidence <= 0:
                    c.confidence = 0.5
                all_candidates.append(c)

        if budget.exhausted and not all_candidates:
            return self._finish_miss(
                ctx,
                attempts,
                providers_tried,
                retries,
                "global_budget_exhausted",
                metrics,
                budget,
                t0,
            )

        ranked = rank_candidates(all_candidates, ctx)
        for idx, (score, cand) in enumerate(ranked):
            metrics["provider_rank"][cand.provider] = {
                "rank": idx + 1,
                "score": round(score, 4),
                "title": cand.title,
            }

        # ── Validation phase (sequential, ranked, within remaining budget) ─
        validated = 0
        for score, cand in ranked:
            if validated >= self.max_attempts:
                break
            if budget.exhausted:
                last_failure = "global_budget_exhausted"
                logger.warning(
                    "Global retrieval budget exhausted during validation",
                    extra={"used_s": round(budget.mark(), 2)},
                )
                break

            if not cand.download_url or cand.extra.get("metadata_only"):
                last_failure = f"{cand.provider}:metadata_only_or_empty_url"
                attempts.append(
                    {
                        "provider": cand.provider,
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
                last_failure = f"{cand.provider}:blocked_url:{why}"
                attempts.append(
                    {
                        "provider": cand.provider,
                        "stage": "url_block",
                        "ok": False,
                        "error": last_failure,
                        "url": cand.download_url,
                    }
                )
                logger.info(
                    "Candidate rejected (blocked URL)",
                    extra={
                        "provider": cand.provider,
                        "url": cand.download_url,
                        "reason": why,
                    },
                )
                retries += 1
                continue

            if not self.validate:
                total_ms = (time.perf_counter() - t0) * 1000
                budget.mark()
                metrics["retrieval_budget_used"] = round(budget.used_s, 3)
                prov = self._build_provenance(cand, validation=None, ctx=ctx)
                metrics["provider_success"][cand.provider] = True
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
                    metrics=metrics,
                )

            wait_s = budget.validation_wait_s()
            val_result, val_timeout, val_err, val_elapsed = run_with_timeout(
                lambda c=cand: self._validate_candidate(c),
                timeout_s=wait_s,
                label=f"val-{cand.provider}",
            )
            val_ms = val_elapsed * 1000
            validated += 1

            if val_timeout:
                last_failure = f"{cand.provider}:validation_timeout"
                attempts.append(
                    {
                        "provider": cand.provider,
                        "stage": "validate",
                        "ok": False,
                        "error": last_failure,
                        "url": cand.download_url,
                        "duration_ms": round(val_ms, 1),
                        "confidence": cand.confidence,
                    }
                )
                retries += 1
                continue

            if val_err or val_result is None:
                last_failure = f"{cand.provider}:validation:{val_err or 'unknown'}"
                attempts.append(
                    {
                        "provider": cand.provider,
                        "stage": "validate",
                        "ok": False,
                        "error": last_failure,
                        "url": cand.download_url,
                        "duration_ms": round(val_ms, 1),
                        "confidence": cand.confidence,
                    }
                )
                retries += 1
                continue

            v = val_result
            attempt = {
                "provider": cand.provider,
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
                "rank_score": cand.extra.get("provider_rank_score") if cand.extra else None,
            }
            attempts.append(attempt)

            logger.info(
                "Candidate validation",
                extra={
                    "provider": cand.provider,
                    "ok": v.ok,
                    "reason": v.reason,
                    "url": cand.download_url,
                    "duration_ms": round(val_ms, 1),
                    "retry_count": retries,
                },
            )

            if not v.ok:
                last_failure = f"{cand.provider}:validation:{v.reason}"
                retries += 1
                continue

            # Success
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
            cand.extra = {
                **(cand.extra or {}),
                "hash": content_hash,
                "content_hash": content_hash,
                "download_date": _utc_now_iso()[:10],
                "provenance": prov,
            }

            total_ms = (time.perf_counter() - t0) * 1000
            budget.mark()
            metrics["retrieval_budget_used"] = round(budget.used_s, 3)
            metrics["provider_success"][cand.provider] = True

            logger.info(
                "Provider orchestrator success",
                extra={
                    "provider": cand.provider,
                    "title": cand.title,
                    "url": cand.download_url,
                    "confidence": cand.confidence,
                    "retry_count": retries,
                    "total_ms": round(total_ms, 1),
                    "budget_used_s": metrics["retrieval_budget_used"],
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
                metrics=metrics,
            )

        return self._finish_miss(
            ctx, attempts, providers_tried, retries, last_failure, metrics, budget, t0
        )

    def _parallel_search(
        self,
        providers: list[DataProvider],
        ctx: TopicContext,
        budget: BudgetSnapshot,
        metrics: dict[str, Any],
        attempts: list[dict[str, Any]],
        providers_tried: list[str],
    ) -> list[tuple[str, list[DatasetCandidate], bool, Optional[str]]]:
        """Run provider searches concurrently; honour per-provider + global budgets."""
        if not providers:
            return []

        workers = max(1, min(self.max_parallel or _max_parallel(), len(providers)))
        metrics["parallel_workers"] = workers
        # Cap each provider by remaining global budget so hung workers cannot
        # outlive the stage (nested threads still wind down after we return).
        provider_timeout = budget.provider_wait_s()
        results: list[tuple[str, list[DatasetCandidate], bool, Optional[str]]] = []
        results_by_name: dict[str, tuple[str, list[DatasetCandidate], bool, Optional[str]]] = {}

        def _run_one(
            provider: DataProvider, timeout_s: float
        ) -> tuple[str, list[DatasetCandidate], bool, Optional[str], float, bool]:
            """Returns name, candidates, ok, error, latency_ms, timed_out."""
            return self._search_provider(provider, ctx, timeout_s)

        # Cap wait by remaining global budget at submit time
        global_wait = max(0.1, budget.remaining_s)
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="ret-prov"
        )
        try:
            future_map: dict[concurrent.futures.Future, DataProvider] = {
                pool.submit(_run_one, p, provider_timeout): p for p in providers
            }
            providers_tried.extend(p.name for p in providers)

            try:
                for future in concurrent.futures.as_completed(
                    future_map, timeout=global_wait
                ):
                    provider = future_map[future]
                    try:
                        name, cands, ok, err, latency_ms, timed_out = future.result(
                            timeout=0
                        )
                    except Exception as exc:
                        name = provider.name
                        cands, ok, err = [], False, str(exc)
                        latency_ms = provider_timeout * 1000
                        timed_out = False

                    metrics["provider_latency_ms"][name] = round(latency_ms, 1)
                    metrics["provider_timeout"][name] = bool(timed_out)
                    metrics["provider_success"][name] = bool(ok and cands)

                    attempt = {
                        "provider": name,
                        "stage": "search",
                        "ok": bool(ok and cands),
                        "error": None if (ok and cands) else (err or "no_candidates"),
                        "duration_ms": round(latency_ms, 1),
                        "timed_out": timed_out,
                        "candidates": len(cands) if cands else 0,
                    }
                    attempts.append(attempt)
                    results_by_name[name] = (name, cands or [], ok, err)

                    logger.info(
                        "Provider search complete",
                        extra={
                            "provider": name,
                            "candidates": len(cands) if cands else 0,
                            "duration_ms": round(latency_ms, 1),
                            "timed_out": timed_out,
                            "ok": ok,
                        },
                    )

                    if budget.exhausted:
                        break
            except concurrent.futures.TimeoutError:
                # Global budget while waiting for stragglers — do not block return
                for future, provider in future_map.items():
                    if future.done():
                        if provider.name not in results_by_name:
                            try:
                                name, cands, ok, err, latency_ms, timed_out = (
                                    future.result(timeout=0)
                                )
                                metrics["provider_latency_ms"][name] = round(
                                    latency_ms, 1
                                )
                                metrics["provider_timeout"][name] = bool(timed_out)
                                metrics["provider_success"][name] = bool(ok and cands)
                                attempts.append(
                                    {
                                        "provider": name,
                                        "stage": "search",
                                        "ok": bool(ok and cands),
                                        "error": None
                                        if (ok and cands)
                                        else (err or "no_candidates"),
                                        "duration_ms": round(latency_ms, 1),
                                        "timed_out": timed_out,
                                        "candidates": len(cands) if cands else 0,
                                    }
                                )
                                results_by_name[name] = (name, cands or [], ok, err)
                            except Exception as exc:
                                results_by_name[provider.name] = (
                                    provider.name,
                                    [],
                                    False,
                                    str(exc),
                                )
                        continue
                    future.cancel()
                    name = provider.name
                    if name in results_by_name:
                        continue
                    used_ms = round(budget.mark() * 1000, 1)
                    metrics["provider_latency_ms"][name] = used_ms
                    metrics["provider_timeout"][name] = True
                    metrics["provider_success"][name] = False
                    attempts.append(
                        {
                            "provider": name,
                            "stage": "search",
                            "ok": False,
                            "error": "global_budget_timeout",
                            "duration_ms": used_ms,
                            "timed_out": True,
                            "candidates": 0,
                        }
                    )
                    results_by_name[name] = (name, [], False, "global_budget_timeout")
                    record_provider_failure(name, "global_budget_timeout")
                    logger.warning(
                        "Provider abandoned (global budget)",
                        extra={"provider": name},
                    )
        finally:
            # Never block /v1/ask on hung provider threads
            pool.shutdown(wait=False, cancel_futures=True)

        # Preserve affinity order for stable metrics/debug
        for p in providers:
            if p.name in results_by_name:
                results.append(results_by_name[p.name])
        return results

    def _search_provider(
        self,
        provider: DataProvider,
        ctx: TopicContext,
        timeout_s: float,
    ) -> tuple[str, list[DatasetCandidate], bool, Optional[str], float, bool]:
        """
        Search one provider with timeout + single network retry.
        Never retries 404/401/403/HTML/login.
        """
        topic = ctx.raw or ctx.normalized
        keywords = ctx.keywords

        def _do_search() -> list[DatasetCandidate]:
            return (
                provider.search(
                    topic,
                    keywords,
                    limit=self.max_candidates_per_provider,
                )
                or []
            )

        value, timed_out, error, elapsed = run_with_timeout(
            _do_search,
            timeout_s=timeout_s,
            label=provider.name,
        )

        # One retry only for retryable network errors (not timeout — already spent budget)
        if error and not timed_out and is_retryable_error(error):
            logger.info(
                "Retrying provider after network error",
                extra={"provider": provider.name, "error": error},
            )
            value2, timed_out2, error2, elapsed2 = run_with_timeout(
                _do_search,
                timeout_s=min(timeout_s, max(0.5, timeout_s * 0.8)),
                label=f"{provider.name}-retry",
            )
            elapsed += elapsed2
            if timed_out2:
                timed_out = True
                error = error2 or error
                value = None
            elif error2 is None:
                value, error, timed_out = value2, None, False
            else:
                error = error2
                value = value2

        latency_ms = elapsed * 1000

        if timed_out:
            record_provider_failure(provider.name, f"timeout:{timeout_s:.1f}s")
            return provider.name, [], False, f"timeout:{timeout_s:.1f}s", latency_ms, True

        if error:
            # Non-retryable auth/not-found still counts as soft failure for circuit
            # only when it looks like infrastructure, not empty catalog
            if is_retryable_error(error):
                record_provider_failure(provider.name, error)
            else:
                # Hard client errors (404/401/403/html) — do not open circuit
                pass
            return provider.name, [], False, error, latency_ms, False

        candidates = value or []
        if candidates:
            record_provider_success(provider.name)
            return provider.name, candidates, True, None, latency_ms, False

        # Soft miss — no candidates is not a circuit failure
        return provider.name, [], False, "no_candidates", latency_ms, False

    @staticmethod
    def _validate_candidate(cand: DatasetCandidate):
        if looks_like_file_url(cand.download_url) or cand.file_format in {
            "csv",
            "json",
            "xlsx",
            "parquet",
            "zip",
            "xls",
        }:
            return probe_download(cand.download_url)
        v = validate_url_metadata(cand.download_url)
        if v.ok:
            return probe_download(cand.download_url)
        return v

    def _finish_miss(
        self,
        ctx: TopicContext,
        attempts: list[dict[str, Any]],
        providers_tried: list[str],
        retries: int,
        last_failure: str,
        metrics: dict[str, Any],
        budget: BudgetSnapshot,
        t0: float,
    ) -> OrchestratorResult:
        total_ms = (time.perf_counter() - t0) * 1000
        budget.mark()
        metrics["retrieval_budget_used"] = round(budget.used_s, 3)
        graceful = self._graceful_message(ctx, providers_tried, last_failure)
        logger.warning(
            "Provider orchestrator exhausted",
            extra={
                "topic": ctx.normalized,
                "retry_count": retries,
                "providers_tried": providers_tried,
                "failure_reason": last_failure,
                "total_ms": round(total_ms, 1),
                "budget_used_s": metrics["retrieval_budget_used"],
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
            metrics=metrics,
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
