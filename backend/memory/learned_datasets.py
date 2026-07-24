"""Growing knowledge base of topics → loadable datasets.

ChatGPT-style product memory (not fine-tuning Ollama weights):
- When a dataset is successfully discovered/uploaded, we *remember* it.
- Next time a similar topic is asked, we recall it first (before live APIs).
- Optional Ollama expands aliases so "yellow metal price" can match "gold rate".
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from sqlalchemy import Column, Float, Integer, String, Text, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core.logger import get_logger
from backend.db import Base, SessionLocal, engine

logger = get_logger(__name__)


class LearnedDataset(Base):
    __tablename__ = "learned_datasets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String, index=True, nullable=False)
    aliases_json = Column(Text, default="[]")
    url = Column(String, nullable=False)
    source = Column(String, default="")
    title = Column(String, default="")
    columns_json = Column(Text, default="[]")
    hit_count = Column(Integer, default=1)
    success_count = Column(Integer, default=1)
    last_used_at = Column(Float, default=0.0)
    created_at = Column(Float, default=0.0)
    notes = Column(Text, default="")


def ensure_learned_schema() -> None:
    Base.metadata.create_all(engine, tables=[LearnedDataset.__table__])


ensure_learned_schema()


def _tokens(text: str) -> set[str]:
    stop = {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by",
        "data", "dataset", "rate", "rates", "price", "prices", "analyze", "forecast",
    }
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 2 and t not in stop
    }


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
    except Exception:
        pass
    return []


def _score_topic(query: str, topic: str, aliases: list[str]) -> float:
    q = (query or "").lower().strip()
    if not q:
        return 0.0

    candidates = [topic, *aliases]
    best = 0.0
    q_tokens = _tokens(q)

    for cand in candidates:
        c = (cand or "").lower().strip()
        if not c:
            continue
        if q == c:
            best = max(best, 100.0)
            continue
        if q in c or c in q:
            best = max(best, 85.0)
            continue
        c_tokens = _tokens(c)
        if not q_tokens or not c_tokens:
            continue
        overlap = len(q_tokens & c_tokens) / max(1, len(q_tokens | c_tokens))
        best = max(best, overlap * 80.0)

    return best


def learn_dataset(
    topic: str,
    url: str,
    *,
    source: str = "",
    title: str = "",
    columns: list[str] | None = None,
    aliases: list[str] | None = None,
    notes: str = "",
    expand_with_llm: bool = True,
) -> dict[str, Any] | None:
    """Remember a successfully loaded dataset for future open-world asks."""
    if not bool(getattr(settings, "LEARN_DATASETS", True)):
        return None

    topic = (topic or "").strip()
    url = (url or "").strip()
    if not topic or not url:
        return None
    # Skip generic placeholders.
    if topic.lower() in {"general dataset", "user provided url", "user provided dataset", "active session dataset"}:
        return None

    now = time.time()
    extra_aliases = list(aliases or [])
    if expand_with_llm and bool(getattr(settings, "USE_LLM_LEARN", True)):
        extra_aliases.extend(_llm_aliases(topic))

    # Always include light rule aliases.
    extra_aliases.extend(_rule_aliases(topic))
    aliases_unique = list(dict.fromkeys(a.strip() for a in extra_aliases if a and a.strip()))

    db: Session = SessionLocal()
    try:
        existing = db.execute(
            select(LearnedDataset).where(
                LearnedDataset.topic == topic,
                LearnedDataset.url == url,
            )
        ).scalar_one_or_none()

        if existing is None:
            # Same URL under different topic spelling → still learn as new topic row
            # but merge aliases into any exact-url match first.
            by_url = db.execute(
                select(LearnedDataset).where(LearnedDataset.url == url)
            ).scalars().first()
            if by_url is not None:
                existing = by_url

        if existing is not None:
            prev = set(_parse_json_list(existing.aliases_json))
            prev.update(aliases_unique)
            prev.add(topic)
            existing.aliases_json = json.dumps(sorted(prev))
            existing.hit_count = int(existing.hit_count or 0) + 1
            existing.success_count = int(existing.success_count or 0) + 1
            existing.last_used_at = now
            if source:
                existing.source = source
            if title:
                existing.title = title
            if columns:
                existing.columns_json = json.dumps(list(columns)[:40])
            if notes:
                existing.notes = notes
            if topic and topic.lower() not in (existing.topic or "").lower():
                # Keep primary topic; add new wording as alias.
                pass
            db.commit()
            logger.info(
                "Updated learned dataset memory",
                extra={"topic": existing.topic, "url": url, "hits": existing.hit_count},
            )
            return _row_to_dict(existing)

        row = LearnedDataset(
            topic=topic,
            aliases_json=json.dumps(aliases_unique),
            url=url,
            source=source or "learned",
            title=title or topic,
            columns_json=json.dumps(list(columns or [])[:40]),
            hit_count=1,
            success_count=1,
            last_used_at=now,
            created_at=now,
            notes=notes or "",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            "Learned new dataset mapping",
            extra={"topic": topic, "url": url, "aliases": aliases_unique[:5]},
        )
        return _row_to_dict(row)
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to learn dataset", extra={"error": str(exc), "topic": topic})
        return None
    finally:
        db.close()


def recall_datasets(topic: str, limit: int = 5, min_score: float = 45.0) -> list[dict[str, Any]]:
    """Recall previously learned datasets for a free-form topic."""
    if not bool(getattr(settings, "LEARN_DATASETS", True)):
        return []

    topic = (topic or "").strip()
    if not topic:
        return []

    db: Session = SessionLocal()
    try:
        rows = db.execute(select(LearnedDataset)).scalars().all()
        scored: list[tuple[float, LearnedDataset]] = []
        for row in rows:
            aliases = _parse_json_list(row.aliases_json)
            score = _score_topic(topic, row.topic or "", aliases)
            # Light boost for frequently successful memories.
            score += min(10.0, float(row.success_count or 0) * 0.5)
            if score >= min_score:
                scored.append((score, row))

        scored.sort(key=lambda item: (item[0], item[1].last_used_at or 0), reverse=True)
        results = []
        for score, row in scored[:limit]:
            payload = _row_to_dict(row)
            payload["rank_hint"] = int(20 + score // 5)
            payload["memory_score"] = round(score, 2)
            payload["loadable"] = True
            results.append(payload)

        if results:
            # Bump hit on best match
            best = scored[0][1]
            best.hit_count = int(best.hit_count or 0) + 1
            best.last_used_at = time.time()
            db.commit()
            logger.info(
                "Recalled learned dataset",
                extra={"topic": topic, "url": results[0].get("url"), "score": results[0].get("memory_score")},
            )
        return results
    except Exception as exc:
        logger.warning("Dataset recall failed", extra={"error": str(exc)})
        return []
    finally:
        db.close()


def list_learned_datasets(limit: int = 50) -> list[dict[str, Any]]:
    db: Session = SessionLocal()
    try:
        rows = (
            db.execute(
                select(LearnedDataset).order_by(LearnedDataset.last_used_at.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
        return [_row_to_dict(row) for row in rows]
    finally:
        db.close()


def _row_to_dict(row: LearnedDataset) -> dict[str, Any]:
    return {
        "id": row.id,
        "topic": row.topic,
        "aliases": _parse_json_list(row.aliases_json),
        "url": row.url,
        "source": row.source or "learned",
        "title": row.title or row.topic,
        "columns": _parse_json_list(row.columns_json),
        "description": f"Learned dataset for {row.topic}",
        "hit_count": row.hit_count,
        "success_count": row.success_count,
        "last_used_at": row.last_used_at,
        "notes": row.notes or "",
    }


def _rule_aliases(topic: str) -> list[str]:
    t = (topic or "").lower().strip()
    aliases = [t, f"{t} dataset", f"{t} csv"]
    mapping = {
        "gold": ["gold price", "gold rate", "bullion", "xau"],
        "gold rate": ["gold", "gold price", "bullion"],
        "gold price": ["gold", "gold rate"],
        "gdp": ["gross domestic product", "economic growth"],
        "population": ["demographics", "people count"],
        "inflation": ["cpi", "consumer price index"],
        "bitcoin": ["btc", "cryptocurrency btc"],
        "oil": ["crude oil", "brent", "wti"],
    }
    for key, values in mapping.items():
        if key in t or t in key:
            aliases.extend(values)
    return aliases


def _llm_aliases(topic: str) -> list[str]:
    """Ask Ollama for short alternate phrasings — ChatGPT-like language understanding."""
    if not topic:
        return []
    try:
        from backend.llm.ollama_client import invoke_llm

        prompt = f"""You help a data analyst product remember dataset topics.
Topic: {topic}

Return ONLY JSON with alternate search phrases people might use for the same data:
{{
  "aliases": ["...", "...", "..."]
}}
Max 5 short aliases. No explanation.
"""
        response = invoke_llm(prompt)
        if not response:
            return []
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end <= start:
            return []
        payload = json.loads(response[start : end + 1])
        aliases = payload.get("aliases") if isinstance(payload, dict) else None
        if not isinstance(aliases, list):
            return []
        return [str(a).strip() for a in aliases if str(a).strip()][:5]
    except Exception as exc:
        logger.info("LLM alias expansion skipped", extra={"error": str(exc)})
        return []
