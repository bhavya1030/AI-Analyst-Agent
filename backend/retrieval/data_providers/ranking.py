"""Candidate ranking when multiple providers succeed (Retrieval v3)."""

from __future__ import annotations

from typing import Sequence

from backend.retrieval.data_providers.base import DatasetCandidate
from backend.retrieval.data_providers.topic import TopicContext

# Higher = more trusted for open tabular data
PROVIDER_TRUST: dict[str, float] = {
    "csv_url": 0.95,
    "world_bank": 0.92,
    "owid": 0.90,
    "fred": 0.88,
    "eurostat": 0.86,
    "github_raw": 0.82,
    "json_api": 0.78,
    "data_gov": 0.72,
    "huggingface": 0.65,
    "kaggle": 0.40,
}


def rank_candidates(
    candidates: Sequence[DatasetCandidate],
    ctx: TopicContext,
) -> list[tuple[float, DatasetCandidate]]:
    """
    Rank by composite score:
      confidence · freshness · provider trust · schema match · size proxy
    Returns list of (score, candidate) descending.
    """
    scored: list[tuple[float, DatasetCandidate]] = []
    for cand in candidates:
        score = _score_one(cand, ctx)
        # stash rank for metrics
        cand.extra = {**(cand.extra or {}), "provider_rank_score": round(score, 4)}
        scored.append((score, cand))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _score_one(cand: DatasetCandidate, ctx: TopicContext) -> float:
    confidence = float(cand.confidence or 0.5)
    trust = PROVIDER_TRUST.get(cand.provider, 0.5)
    freshness = _freshness_score(cand)
    schema = _schema_match(cand, ctx)
    size = _size_score(cand)
    # Weighted blend
    return (
        0.35 * confidence
        + 0.25 * trust
        + 0.15 * freshness
        + 0.15 * schema
        + 0.10 * size
    )


def _freshness_score(cand: DatasetCandidate) -> float:
    # Prefer explicit version / recent tags; default neutral
    ver = (cand.dataset_version or "").lower()
    if "master" in ver or "latest" in ver:
        return 0.85
    if ver:
        return 0.75
    tags = {t.lower() for t in (cand.tags or [])}
    if "live" in tags or "realtime" in tags:
        return 0.9
    return 0.6


def _schema_match(cand: DatasetCandidate, ctx: TopicContext) -> float:
    score = 0.5
    blob = f"{cand.title} {cand.description} {' '.join(cand.tags or [])}".lower()
    if ctx.metric and ctx.metric.lower().split()[0] in blob:
        score += 0.25
    if ctx.aliases and any(a.replace("_", " ") in blob or a in blob for a in ctx.aliases):
        score += 0.15
    if ctx.country and any(c.lower() in blob for c in ctx.country):
        score += 0.1
    if ctx.domain != "general" and ctx.domain in blob:
        score += 0.05
    return min(1.0, score)


def _size_score(cand: DatasetCandidate) -> float:
    """Prefer mid-size datasets (enough rows, not pathological)."""
    extra = cand.extra or {}
    size = extra.get("size_bytes") or extra.get("dataset_size")
    if size is None:
        return 0.55
    try:
        n = int(size)
    except Exception:
        return 0.55
    if n < 64:
        return 0.2
    if n < 1024:
        return 0.4
    if n < 50 * 1024 * 1024:
        return 0.85
    if n < 80 * 1024 * 1024:
        return 0.6
    return 0.3
