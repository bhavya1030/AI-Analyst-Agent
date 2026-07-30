"""High-confidence Dataset Registry matching.

Combines topic, domain, intent, keywords, columns, country, and optional
semantic similarity. Rejects low-confidence and conflicting matches so
false positives like Olympics→GDP or Atlantis→World Bank GDP never become
REGISTRY_HIT.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional, Sequence

from backend.config import settings
from backend.core.logger import get_logger
from backend.registry.models import DatasetMetadata

logger = get_logger(__name__)

# Default threshold for accepting a registry match (0–1).
DEFAULT_MIN_CONFIDENCE = float(
    getattr(settings, "REGISTRY_MIN_CONFIDENCE", 0.62)
)
# Semantic-only gate (used when embedding score is available).
DEFAULT_SEMANTIC_FLOOR = float(
    getattr(settings, "REGISTRY_SEMANTIC_FLOOR", 0.45)
)

_STOP = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by",
    "data", "dataset", "datasets", "open", "csv", "json", "analyze", "analyse",
    "study", "explore", "show", "visualize", "visualise", "trends", "trend",
    "global", "world", "worldwide", "using", "about", "from", "over", "time",
    "rates", "statistics", "index", "counts", "count", "major", "cities",
}

# Strong domain tokens — presence implies a domain cluster.
DOMAIN_LEXICON: dict[str, set[str]] = {
    "macroeconomics": {
        "gdp", "inflation", "cpi", "unemployment", "macro", "interest", "trade",
        "balance", "fiscal", "monetary",
    },
    "demographics": {"population", "demographic", "birth", "mortality", "fertility"},
    "climate": {"co2", "emission", "emissions", "climate", "temperature", "carbon", "ghg"},
    "energy": {"energy", "renewable", "solar", "wind", "electricity", "oil", "gas", "coal"},
    "transport": {"ev", "electric", "vehicle", "vehicles", "transport", "car", "traffic"},
    "sports": {"olympic", "olympics", "medal", "medals", "athlete", "sport", "games", "games"},
    "health": {"covid", "health", "disease", "hospital", "mortality", "life", "expectancy"},
    "technology": {"internet", "broadband", "digital", "telecom", "mobile"},
    "tourism": {"tourism", "tourist", "arrivals", "travel", "hotel"},
    "finance": {"bitcoin", "crypto", "cryptocurrency", "stock", "equity", "gold", "silver", "price"},
    "environment": {"air", "pollution", "aqi", "pm25", "water", "quality"},
    "wellbeing": {"happiness", "wellbeing", "well-being", "satisfaction"},
}

# Domains that must not cross-match without strong evidence.
DOMAIN_CONFLICTS: dict[str, set[str]] = {
    "sports": {"macroeconomics", "demographics", "finance", "climate", "energy"},
    "olympics": {"macroeconomics", "finance", "climate", "demographics"},
    "macroeconomics": {"sports", "transport", "olympics"},
    "demographics": {"sports", "finance", "cryptocurrency"},
    "finance": {"sports", "demographics", "tourism"},
    "transport": {"macroeconomics", "sports"},
    "climate": {"sports", "olympics"},
    "tourism": {"sports", "cryptocurrency"},
    "technology": {"sports"},
    "health": {"sports", "finance"},
}

# Fictional / nonsense entities — never accept registry macro datasets.
FICTIONAL_ENTITIES = {
    "atlantis", "unicorn", "dragon", "xyzabc", "xyzabc123", "narnia", "wakanda",
    "middleearth", "hogwarts", "gotham", "asgard",
}

# Column name hints by domain / intent
DOMAIN_COLUMN_HINTS: dict[str, set[str]] = {
    "macroeconomics": {"gdp", "value", "year", "country", "code", "inflation", "cpi"},
    "demographics": {"population", "year", "country", "value"},
    "sports": {"medal", "gold", "silver", "bronze", "athlete", "sport", "event", "noc", "team", "games", "year"},
    "climate": {"co2", "emission", "year", "country", "temperature"},
    "energy": {"energy", "electricity", "renewable", "year", "country"},
    "finance": {"price", "close", "open", "volume", "date", "year"},
    "tourism": {"arrivals", "tourists", "year", "country", "value"},
    "technology": {"internet", "users", "year", "country", "value"},
}


@dataclass
class MatchQuery:
    """Normalized query signals for registry matching."""

    raw: str
    topic: str
    keywords: list[str] = field(default_factory=list)
    domain: str = "general"
    intent: str = "analyze"
    countries: list[str] = field(default_factory=list)
    column_hints: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    question: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MatchScore:
    """Scored registry candidate with explainability."""

    dataset_id: str
    confidence: float
    accepted: bool
    explanation: str
    reasons: list[str] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    metadata: Optional[DatasetMetadata] = None
    semantic_score: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "confidence": self.confidence,
            "accepted": self.accepted,
            "explanation": self.explanation,
            "reasons": self.reasons,
            "rejections": self.rejections,
            "components": self.components,
            "semantic_score": self.semantic_score,
            "title": self.metadata.title if self.metadata else None,
            "topic": self.metadata.topic if self.metadata else None,
            "domain": getattr(self.metadata, "domain", None) if self.metadata else None,
        }


def tokenize(text: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 2 and t not in _STOP
    ]


def infer_domain(text: str, *, tags: Sequence[str] | None = None) -> str:
    blob = f"{text or ''} {' '.join(tags or [])}".lower()
    tokens = set(tokenize(blob)) | set(re.findall(r"[a-z0-9]+", blob))
    best = "general"
    best_hits = 0
    for domain, lexicon in DOMAIN_LEXICON.items():
        hits = len(tokens & lexicon)
        if hits > best_hits:
            best_hits = hits
            best = domain
    return best if best_hits else "general"


def infer_intent(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ("forecast", "predict", "projection", "next year", "future")):
        return "forecast"
    if any(w in t for w in ("compare", "vs", "versus", "difference between")):
        return "compare"
    if any(w in t for w in ("correlation", "heatmap", "relationship")):
        return "correlation"
    if any(w in t for w in ("chart", "plot", "visual", "graph")):
        return "visualize"
    if any(w in t for w in ("top ", "rank", "highest", "lowest")):
        return "rank"
    return "analyze"


def extract_countries(text: str) -> list[str]:
    # Lightweight country lexicon for matching (not exhaustive geopolitics)
    known = {
        "india", "china", "usa", "united states", "us", "uk", "united kingdom",
        "japan", "germany", "france", "brazil", "canada", "australia", "mexico",
        "russia", "indonesia", "nigeria", "pakistan", "bangladesh", "ethiopia",
    }
    t = (text or "").lower()
    found = []
    for c in sorted(known, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", t):
            found.append(c)
    return found


_ALIAS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(electric\s*vehicle|ev\s*sales|\bev\b|electric car)", re.I), "electric_vehicles"),
    (re.compile(r"\b(co2|co₂|carbon\s*dioxide|carbon\s*emission|greenhouse)", re.I), "co2_emissions"),
    (re.compile(r"\b(renewable|solar\s*energy|wind\s*energy|clean\s*energy)", re.I), "renewable_energy"),
    (re.compile(r"\b(happiness|world\s*happiness)", re.I), "happiness"),
    (re.compile(r"\b(air\s*quality|aqi|pm2\.?5|pollution\s*index)", re.I), "air_quality"),
    (re.compile(r"\b(inflation|cpi|consumer\s*price)", re.I), "inflation"),
    (re.compile(r"\b(bitcoin|crypto|cryptocurrency|ethereum)", re.I), "cryptocurrency"),
    (re.compile(r"\b(olympic|olympics|medal\s*count)", re.I), "olympics"),
    (re.compile(r"\b(internet\s*usage|internet\s*users|broadband)", re.I), "internet_usage"),
    (re.compile(r"\b(tourism|tourist|tourist\s*arrivals)", re.I), "tourism"),
    (re.compile(r"\b(gdp|gross\s*domestic)", re.I), "gdp"),
    (re.compile(r"\b(population|demograph)", re.I), "population"),
    (re.compile(r"\b(unemployment|jobless)", re.I), "unemployment"),
    (re.compile(r"\b(gold(\s*price)?)", re.I), "gold"),
    (re.compile(r"\b(covid|coronavirus)", re.I), "covid"),
]


def _extract_aliases(text: str) -> list[str]:
    aliases: list[str] = []
    for pattern, key in _ALIAS_PATTERNS:
        if pattern.search(text or ""):
            if key not in aliases:
                aliases.append(key)
    return aliases


def build_match_query(
    topic: str,
    *,
    question: str | None = None,
    intent: str | None = None,
) -> MatchQuery:
    raw = (topic or question or "").strip()
    combined = f"{topic or ''} {question or ''}".strip()
    normalized = re.sub(r"\s+", " ", raw.lower()).strip()
    keywords = list(dict.fromkeys(tokenize(combined)))
    aliases = _extract_aliases(combined)
    domain = infer_domain(combined, tags=aliases)
    # Alias → domain boost
    alias_domain = {
        "gdp": "macroeconomics",
        "population": "demographics",
        "co2_emissions": "climate",
        "renewable_energy": "energy",
        "electric_vehicles": "transport",
        "olympics": "sports",
        "inflation": "macroeconomics",
        "cryptocurrency": "finance",
        "internet_usage": "technology",
        "tourism": "tourism",
        "air_quality": "environment",
        "happiness": "wellbeing",
        "gold": "finance",
        "covid": "health",
    }
    for a in aliases:
        if a in alias_domain:
            domain = alias_domain[a]
            break
    countries = extract_countries(combined)
    col_hints = list(DOMAIN_COLUMN_HINTS.get(domain, set()))
    return MatchQuery(
        raw=raw,
        topic=(topic or normalized or raw).strip().lower(),
        keywords=keywords,
        domain=domain,
        intent=intent or infer_intent(combined),
        countries=countries,
        column_hints=col_hints,
        aliases=aliases,
        question=(question or "").strip(),
    )


def _meta_domain(meta: DatasetMetadata) -> str:
    explicit = (getattr(meta, "domain", None) or "").strip().lower()
    if explicit and explicit != "general":
        return explicit
    tags = list(meta.tags or [])
    return infer_domain(
        f"{meta.topic} {meta.title} {meta.description} {meta.summary}",
        tags=tags,
    )


def _meta_keywords(meta: DatasetMetadata) -> set[str]:
    kws = set()
    for item in getattr(meta, "keywords", None) or []:
        kws.add(str(item).lower())
    for t in meta.tags or []:
        # strip provenance prefixes
        s = str(t).lower()
        if s.startswith(("provider:", "license:", "version:")):
            continue
        kws.update(tokenize(s))
        kws.add(s)
    kws.update(tokenize(meta.topic or ""))
    kws.update(tokenize(meta.title or ""))
    return {k for k in kws if k and k not in _STOP}


def _meta_countries(meta: DatasetMetadata) -> set[str]:
    out = set()
    for c in getattr(meta, "country", None) or getattr(meta, "countries", None) or []:
        out.add(str(c).lower())
    # parse from tags like country:india
    for t in meta.tags or []:
        s = str(t).lower()
        if s.startswith("country:"):
            out.add(s.split(":", 1)[1])
    out.update(extract_countries(f"{meta.topic} {meta.title} {meta.description}"))
    return out


def _meta_columns(meta: DatasetMetadata) -> set[str]:
    cols = set()
    for c in meta.columns or []:
        cols.add(str(c).lower())
        cols.update(tokenize(str(c)))
    return cols


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _token_overlap(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), 1)


def score_dataset(
    query: MatchQuery,
    meta: DatasetMetadata,
    *,
    semantic_score: float | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> MatchScore:
    """Score one registry record against the query; may hard-reject."""
    reasons: list[str] = []
    rejections: list[str] = []
    components: dict[str, float] = {}

    q_tokens = set(query.keywords) | set(tokenize(query.topic))
    m_topic = (meta.topic or "").lower().strip()
    m_title = (meta.title or "").lower().strip()
    m_domain = _meta_domain(meta)
    m_keywords = _meta_keywords(meta)
    m_countries = _meta_countries(meta)
    m_columns = _meta_columns(meta)

    # --- Hard rejects -------------------------------------------------
    # Fictional entities in query must not bind real world datasets
    fiction_hits = [e for e in FICTIONAL_ENTITIES if e in query.raw.lower() or e in query.topic]
    if fiction_hits:
        # Allow only if the same fictional token is explicitly in the dataset topic/title
        if not any(e in m_topic or e in m_title for e in fiction_hits):
            rejections.append(
                f"Fictional/nonsense entity {fiction_hits} cannot match real registry dataset "
                f"'{meta.title or meta.topic}'."
            )

    # Domain conflict (e.g. sports query vs macro dataset)
    q_domain = query.domain or "general"
    if q_domain != "general" and m_domain != "general" and q_domain != m_domain:
        conflicts = DOMAIN_CONFLICTS.get(q_domain, set())
        if m_domain in conflicts or q_domain in DOMAIN_CONFLICTS.get(m_domain, set()):
            rejections.append(
                f"Domain conflict: query domain '{q_domain}' vs dataset domain '{m_domain}'."
            )

    # Strong token conflict: query has olympics/medal but dataset has gdp-only identity
    sports_q = bool({"olympic", "olympics", "medal", "medals", "athlete"} & q_tokens)
    macro_ds = bool({"gdp", "inflation", "cpi"} & m_keywords) or m_domain == "macroeconomics"
    if sports_q and macro_ds and not ({"olympic", "olympics", "medal"} & m_keywords):
        rejections.append("Sports/olympics query cannot match GDP/macro registry dataset.")

    # Inverse: GDP query must never match Olympics / sports-only datasets
    macro_q = bool({"gdp", "inflation", "cpi", "unemployment"} & q_tokens) or (
        query.domain == "macroeconomics"
    )
    sports_ds = (
        bool({"olympic", "olympics", "medal", "medals", "athlete"} & m_keywords)
        or m_domain in {"sports", "olympics"}
        or "olympic" in m_topic
        or "olympic" in m_title
    )
    if macro_q and sports_ds and not ({"gdp", "inflation", "cpi"} & m_keywords):
        rejections.append("GDP/macro query cannot match Olympics/sports registry dataset.")

    unicorn_pop = "unicorn" in query.raw.lower() and (
        "population" in m_topic or m_domain == "demographics"
    )
    if unicorn_pop:
        rejections.append("Fictional 'unicorn population' cannot match real population dataset.")

    if rejections:
        return MatchScore(
            dataset_id=meta.dataset_id,
            confidence=0.0,
            accepted=False,
            explanation="; ".join(rejections),
            reasons=[],
            rejections=rejections,
            components={},
            metadata=meta,
            semantic_score=semantic_score,
        )

    # --- Component scores ---------------------------------------------
    # Topic
    m_topic_tokens = set(tokenize(m_topic + " " + m_title))
    if m_topic and m_topic == query.topic:
        topic_score = 1.0
        reasons.append(f"Exact topic match ('{m_topic}').")
    elif m_topic and m_topic in query.topic:
        # Query is broader phrasing of the same dataset topic (common in NL asks)
        topic_score = 0.88
        reasons.append(f"Dataset topic is contained in query ('{m_topic}').")
    elif m_topic and query.topic in m_topic:
        ratio = len(query.topic) / max(len(m_topic), 1)
        topic_score = max(0.55, 0.9 * ratio)
        reasons.append(f"Query topic contained in dataset topic ('{query.topic}').")
    else:
        topic_score = _jaccard(q_tokens, m_topic_tokens)
        # Boost when all significant dataset tokens appear in the query
        if m_topic_tokens and m_topic_tokens.issubset(q_tokens):
            topic_score = max(topic_score, 0.82)
            reasons.append("All dataset topic tokens present in query.")
        elif topic_score >= 0.35:
            reasons.append(f"Topic token Jaccard={topic_score:.2f}.")
    components["topic"] = round(topic_score, 3)

    # Domain
    if q_domain == "general" or m_domain == "general":
        domain_score = 0.45 if q_domain == m_domain else 0.35
    elif q_domain == m_domain:
        domain_score = 1.0
        reasons.append(f"Domain aligned ('{q_domain}').")
    else:
        domain_score = 0.1
        reasons.append(f"Domain weak mismatch ('{q_domain}' vs '{m_domain}').")
    components["domain"] = round(domain_score, 3)

    # Keywords / tags
    kw_score = _jaccard(q_tokens, m_keywords)
    if kw_score >= 0.25:
        reasons.append(f"Keyword/tag overlap={kw_score:.2f}.")
    components["keywords"] = round(kw_score, 3)

    # Columns
    if query.column_hints and m_columns:
        col_score = _token_overlap(
            {h.lower() for h in query.column_hints},
            m_columns,
        )
        if col_score >= 0.2:
            reasons.append(f"Column hint overlap={col_score:.2f}.")
    elif m_columns and q_tokens:
        col_score = _token_overlap(q_tokens, m_columns) * 0.8
    else:
        col_score = 0.25  # neutral when unknown
    components["columns"] = round(col_score, 3)

    # Country
    if query.countries:
        if m_countries:
            country_score = 1.0 if set(query.countries) & m_countries else 0.15
            if country_score >= 1.0:
                reasons.append(f"Country match {sorted(set(query.countries) & m_countries)}.")
            else:
                reasons.append("Country requested but not present on dataset.")
        else:
            country_score = 0.4  # dataset is global — soft accept
            reasons.append("Country requested; dataset has no country filter (treated as global).")
    else:
        country_score = 0.5
    components["country"] = round(country_score, 3)

    # Intent (forecast needs time-like columns)
    if query.intent == "forecast":
        timeish = any(
            any(k in c for k in ("year", "date", "time", "month"))
            for c in m_columns
        )
        intent_score = 0.9 if timeish else 0.35
        if timeish:
            reasons.append("Intent=forecast supported by time-like columns.")
        else:
            reasons.append("Intent=forecast but no clear time column on dataset.")
    elif query.intent == "compare":
        intent_score = 0.8 if m_columns else 0.5
    else:
        intent_score = 0.6
    components["intent"] = round(intent_score, 3)

    # Semantic (optional)
    if semantic_score is not None:
        sem = max(0.0, min(1.0, float(semantic_score)))
        components["semantic"] = round(sem, 3)
        if sem >= DEFAULT_SEMANTIC_FLOOR:
            reasons.append(f"Embedding similarity={sem:.3f}.")
        else:
            reasons.append(f"Embedding similarity low ({sem:.3f}).")
    else:
        sem = None
        components["semantic"] = 0.0

    # Weighted confidence
    weights = {
        "topic": 0.28,
        "domain": 0.20,
        "keywords": 0.14,
        "columns": 0.12,
        "country": 0.08,
        "intent": 0.08,
        "semantic": 0.10 if sem is not None else 0.0,
    }
    # redistrib if no semantic
    if sem is None:
        boost = 0.10 / 6
        for k in ("topic", "domain", "keywords", "columns", "country", "intent"):
            weights[k] += boost

    confidence = sum(components[k] * weights[k] for k in weights)
    confidence = max(0.0, min(1.0, confidence))

    # Exact topic identity is a strong signal even with sparse tags/columns
    if m_topic and m_topic == query.topic:
        confidence = max(confidence, 0.78)
        components["topic"] = max(components.get("topic", 0), 1.0)

    # Require minimum topic OR keyword signal for non-exact matches
    if topic_score < 0.40 and kw_score < 0.20 and (sem is None or sem < 0.55):
        rejections.append(
            "Insufficient topic/keyword/semantic evidence for a safe registry match."
        )
        return MatchScore(
            dataset_id=meta.dataset_id,
            confidence=round(confidence * 0.4, 3),
            accepted=False,
            explanation="; ".join(rejections),
            reasons=reasons,
            rejections=rejections,
            components=components,
            metadata=meta,
            semantic_score=semantic_score,
        )

    if sem is not None and sem < DEFAULT_SEMANTIC_FLOOR and topic_score < 0.7:
        rejections.append(
            f"Semantic score {sem:.3f} below floor {DEFAULT_SEMANTIC_FLOOR} "
            "without strong topic match."
        )
        return MatchScore(
            dataset_id=meta.dataset_id,
            confidence=round(min(confidence, sem), 3),
            accepted=False,
            explanation="; ".join(rejections),
            reasons=reasons,
            rejections=rejections,
            components=components,
            metadata=meta,
            semantic_score=semantic_score,
        )

    accepted = confidence >= min_confidence
    if accepted:
        reasons.append(f"Confidence {confidence:.3f} ≥ threshold {min_confidence:.2f}.")
        explanation = (
            f"Selected '{meta.title or meta.topic}' (id={meta.dataset_id}) "
            f"with confidence {confidence:.3f}. " + " ".join(reasons)
        )
    else:
        rejections.append(
            f"Confidence {confidence:.3f} below threshold {min_confidence:.2f}."
        )
        explanation = "; ".join(rejections)

    return MatchScore(
        dataset_id=meta.dataset_id,
        confidence=round(confidence, 3),
        accepted=accepted,
        explanation=explanation,
        reasons=reasons,
        rejections=rejections,
        components=components,
        metadata=meta,
        semantic_score=semantic_score,
    )


def match_registry(
    topic: str,
    candidates: Sequence[DatasetMetadata],
    *,
    question: str | None = None,
    intent: str | None = None,
    semantic_scores: dict[str, float] | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    limit: int = 5,
) -> list[MatchScore]:
    """Score all candidates; return accepted matches sorted by confidence desc."""
    query = build_match_query(topic, question=question, intent=intent)
    scored: list[MatchScore] = []
    for meta in candidates:
        if not meta or not getattr(meta, "is_active", True):
            continue
        sem = None
        if semantic_scores and meta.dataset_id in semantic_scores:
            sem = semantic_scores[meta.dataset_id]
        scored.append(
            score_dataset(
                query,
                meta,
                semantic_score=sem,
                min_confidence=min_confidence,
            )
        )

    accepted = [s for s in scored if s.accepted]
    accepted.sort(key=lambda s: s.confidence, reverse=True)

    logger.info(
        "Registry match complete",
        extra={
            "topic": query.topic,
            "domain": query.domain,
            "candidates": len(list(candidates)),
            "accepted": len(accepted),
            "top_confidence": accepted[0].confidence if accepted else 0,
            "top_id": accepted[0].dataset_id if accepted else None,
        },
    )
    return accepted[: max(1, limit)] if accepted else []


def best_match(
    topic: str,
    candidates: Sequence[DatasetMetadata],
    **kwargs: Any,
) -> Optional[MatchScore]:
    hits = match_registry(topic, candidates, **kwargs)
    return hits[0] if hits else None
