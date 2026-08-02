import json
import re

from backend.config import settings
from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm
from backend.utils.dataset_resolver import looks_like_direct_url

logger = get_logger(__name__)

DATASET_TOPIC_KEYWORDS = {
    "macroeconomic": ["gdp", "inflation", "employment", "unemployment", "population", "income", "economic"],
    "climate": ["co2", "temperature", "rain", "climate", "emissions", "carbon", "weather"],
    "education": ["student", "school", "education", "literacy", "test", "score", "grade"],
    "demographic": ["population", "age", "gender", "birth", "mortality", "ethnicity", "race"],
    "financial": ["revenue", "profit", "sales", "expense", "cost", "price", "stock"],
    "health": ["health", "disease", "hospital", "mortality", "covid", "vaccination"],
}

# Explicit metric tokens that map cleanly to catalog/search keys.
METRIC_TOKENS = [
    "gdp",
    "population",
    "inflation",
    "unemployment",
    "climate",
    "temperature",
    "co2",
    "covid",
    "sales",
    "revenue",
    "stock",
    "energy",
    "electric vehicle",
    "ev",
    "housing",
    "titanic",
    "iris",
    "gold",
    "gold price",
    "gold rate",
    "silver",
    "oil",
]

COUNTRY_HINTS = [
    "india",
    "united states",
    "usa",
    "us",
    "china",
    "japan",
    "germany",
    "brazil",
    "uk",
    "united kingdom",
    "canada",
    "france",
    "australia",
]

# Verbs/noise stripped so free-form topics become searchable phrases.
_STRIP_PATTERN = re.compile(
    r"\b("
    r"analyze|analyse|analysis|study|explore|investigate|show|plot|chart|graph|"
    r"forecast|predict|compare|visualize|visualise|display|summarize|summarise|"
    r"summary|find|fetch|download|get|search|dataset|data|about|on|of|the|a|an|"
    r"for|next|previous|past|last|coming|upcoming|please|help|me|with|using|"
    r"over|across|deeply|trend|trends|rate|rates|price|prices|history|historical|"
    r"growth|and|to|from|years?|months?|days?"
    r")\b",
    re.IGNORECASE,
)

# Keep commodity/subject words that the strip list might otherwise remove when
# they are the actual topic (e.g. "gold rate" → keep "gold").
_TOPIC_KEEP_TOKENS = {
    "gold",
    "silver",
    "oil",
    "bitcoin",
    "crypto",
    "stock",
    "gdp",
    "inflation",
    "population",
    "covid",
    "climate",
    "temperature",
}


def dataset_topic_agent(state):
    question = (state.get("question") or "").strip()

    # Direct URL in the question → treat as user-connected source.
    url_match = _extract_url(question)
    if url_match:
        state["dataset_url"] = url_match
        state["dataset_topic"] = state.get("dataset_topic") or "user provided url"
        state["source"] = "direct_url"
        state["search_queries"] = []
        logger.info(
            "Dataset topic resolved from direct URL",
            extra={"action": "dataset_topic_agent", "url": url_match},
        )
        return state

    # Fast deterministic path — critical for product UX latency.
    topic = _extract_topic_from_question(question)
    rule_topic = topic

    # Ollama for free-form subjects only when rules are weak/empty.
    # Do NOT block rediscovery of clear topics like "gold" waiting on LLM.
    use_llm = bool(getattr(settings, "USE_LLM_TOPIC", False))
    needs_llm = use_llm and (not topic or _topic_is_weak(topic))

    if question and needs_llm:
        prompt = f"""
You are a dataset topic extractor for an analytics copilot.
Extract the real-world data subject the user wants (not analysis verbs).

Examples:
"Analyze GDP growth" -> {{"dataset_topic": "GDP", "search_queries": ["GDP", "GDP by country csv"]}}
"Analyze India's GDP" -> {{"dataset_topic": "India GDP", "search_queries": ["India GDP", "GDP India annual"]}}
"gold rate previous 5 years predict next 5" -> {{"dataset_topic": "gold price", "search_queries": ["gold price annual", "gold rate historical csv"]}}
"Study electric vehicle adoption" -> {{"dataset_topic": "electric vehicle adoption", "search_queries": ["EV adoption", "electric vehicle sales"]}}

Return ONLY JSON:
{{
  "dataset_topic": "...",
  "search_queries": ["...", "..."]
}}

User question:
{question}

Rule-based guess (may be incomplete): {rule_topic or "none"}
"""
        try:
            response = invoke_llm(prompt)
            parsed = _parse_topic_response(response)
            llm_topic = parsed.get("topic") or ""
            queries = parsed.get("search_queries") or []
            if llm_topic:
                topic = llm_topic
                state["dataset_topic"] = topic
                state["search_queries"] = queries or _build_search_queries(topic, question)
                state["topic_via_llm"] = True
                _extract_focus_entities(state, question)
                logger.info(
                    "Dataset topic resolved with Ollama",
                    extra={"action": "dataset_topic_agent", "dataset_topic": topic},
                )
                return state
        except Exception as exc:
            logger.warning(
                "Topic LLM extraction failed",
                extra={"error": str(exc)},
            )

    if topic:
        state["dataset_topic"] = topic
        state["search_queries"] = _build_search_queries(topic, question)
        _extract_focus_entities(state, question)
        logger.info(
            "Dataset topic resolved without LLM",
            extra={"action": "dataset_topic_agent", "dataset_topic": topic},
        )
        return state

    return _fallback_topic(state, question)


def _topic_is_weak(topic: str) -> bool:
    tokens = [t for t in (topic or "").lower().split() if t]
    if not tokens:
        return True
    if len(tokens) == 1 and tokens[0] in {"data", "dataset", "analysis", "trend"}:
        return True
    # Only digits/noise
    if all(t.isdigit() for t in tokens):
        return True
    return False


def _extract_url(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"https?://[^\s<>\"']+", text)
    if not match:
        return None
    url = match.group(0).rstrip(").,;]")
    if looks_like_direct_url(url):
        return url
    return None


def _extract_topic_from_question(question: str) -> str:
    if not question:
        return ""

    # Shared topic detection (filename/question heuristics)
    try:
        from backend.metadata.topic_detection import topic_from_question

        shared = topic_from_question(question)
        if shared:
            # Keep lower-case style for search keys when phrase is multi-word free form
            # but preserve display-friendly country/metric titles from compose.
            return shared[:120]
    except Exception:
        pass

    normalized = question.lower()
    # Preserve known subject tokens before stripping filler (gold rate → gold).
    kept = [tok for tok in _TOPIC_KEEP_TOKENS if re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", normalized)]
    cleaned = _STRIP_PATTERN.sub(" ", normalized)
    # Drop horizon numbers left over from "previous 5 years" / "next 10 years".
    cleaned = re.sub(r"\b\d+\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if kept:
        # Prefer explicit commodity/subject + residual cleaned phrase.
        residual = [w for w in cleaned.split() if w not in kept]
        cleaned = " ".join(kept + residual).strip()

    metrics = [
        token
        for token in sorted(METRIC_TOKENS, key=len, reverse=True)
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", normalized)
    ]
    # Prefer longest phrase only (e.g. "gold rate" over bare "gold").
    if metrics:
        primary = metrics[0]
        metrics = [primary] + [
            m for m in metrics[1:] if m not in primary and primary not in m
        ]
    countries = []
    for country in sorted(COUNTRY_HINTS, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(country)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            if country in {"usa", "us"}:
                label = "united states"
            elif country == "uk":
                label = "united kingdom"
            else:
                label = country
            if label not in countries:
                countries.append(label)

    free_form = cleaned if cleaned not in {"", "data", "dataset", "it", "this", "that"} else ""
    free_tokens = [t for t in free_form.split() if t]

    # Words explained by country/metric shortcuts (plus trivial glue).
    covered = set()
    for country in countries:
        covered.update(country.split())
    for metric in metrics:
        covered.update(metric.split())
    covered.update({"united", "states", "kingdom"})
    residual = [t for t in free_tokens if t not in covered]

    # Classic short asks ("india gdp") → structured topic.
    # Rich asks ("video game sales", "penguin body measurements") → keep full phrase
    # so we don't map "sales" alone onto tips.csv.
    if metrics and len(residual) == 0 and len(free_tokens) <= 4:
        parts = []
        if countries:
            parts.extend(countries)
        parts.extend(metrics)
        topic = " ".join(parts).strip()
    elif free_form:
        topic = free_form
    elif metrics:
        topic = " ".join(metrics)
    elif countries:
        topic = " ".join(countries)
    else:
        topic = ""

    # Cap length so search APIs stay focused.
    if len(topic) > 120:
        topic = " ".join(topic.split()[:12])
    return topic


def _build_search_queries(topic: str, question: str = "") -> list[str]:
    base = (topic or "").strip()
    if not base:
        return []
    queries = [
        base,
        f"{base} dataset",
        f"{base} csv",
        f"{base} open data",
    ]
    # Keep a lightly cleaned original question fragment for broader recall.
    if question:
        fragment = _STRIP_PATTERN.sub(" ", question.lower())
        fragment = re.sub(r"\s+", " ", fragment).strip()
        if fragment and fragment not in queries:
            queries.append(fragment)
    return list(dict.fromkeys(q for q in queries if q))[:6]


def _extract_focus_entities(state, question: str):
    """Attach optional country/metric focus for data engineering filters."""
    normalized = (question or "").lower()
    for country in sorted(COUNTRY_HINTS, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(country)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            if country in {"usa", "us"}:
                state["focus_country"] = "United States"
            elif country == "uk":
                state["focus_country"] = "United Kingdom"
            elif country == "india":
                state["focus_country"] = "India"
            else:
                state["focus_country"] = country.title()
            break

    for metric in METRIC_TOKENS:
        if metric in normalized:
            state["focus_metric"] = metric
            break


def _parse_topic_response(response: str) -> dict:
    if not response:
        return {}

    try:
        payload = json.loads(response)
    except Exception:
        payload = _extract_json(response)
        if payload:
            try:
                payload = json.loads(payload)
            except Exception:
                return {}
        else:
            return {}

    if not isinstance(payload, dict):
        return {}

    topic = payload.get("dataset_topic") or payload.get("topic")
    queries = payload.get("search_queries") or []
    result = {}
    if isinstance(topic, str) and topic.strip():
        result["topic"] = topic.strip()
    if isinstance(queries, list):
        result["search_queries"] = [str(q).strip() for q in queries if str(q).strip()]
    return result


def _extract_json(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _fallback_topic(state, question: str = ""):
    topic = _extract_topic_from_question(question or state.get("question") or "")
    if topic:
        state["dataset_topic"] = topic
        state["search_queries"] = _build_search_queries(topic, question)
        _extract_focus_entities(state, question or state.get("question") or "")
        return state

    columns = state.get("columns") or []
    file_hint = state.get("file_path") or state.get("local_path") or state.get("dataset_url")

    # Prefer structure-aware topic detection (filename + columns + values)
    try:
        from backend.metadata.topic_detection import topic_from_columns_and_values
        from backend.metadata.models import is_placeholder_label

        sample_values: list = []
        data = state.get("data")
        if data is not None and hasattr(data, "columns"):
            for col in list(data.columns)[:3]:
                try:
                    sample_values.extend(
                        [str(v) for v in data[col].dropna().astype(str).head(20).tolist()]
                    )
                except Exception:
                    pass

        structured = topic_from_columns_and_values(
            columns,
            sample_values=sample_values,
            filename=str(file_hint) if file_hint else None,
            question=question or state.get("question"),
        )
        if structured and not is_placeholder_label(structured):
            state["dataset_topic"] = structured
            state["dataset_name"] = structured
            state["search_queries"] = _build_search_queries(structured, question)
            _extract_focus_entities(state, question or state.get("question") or "")
            return state
    except Exception as exc:
        logger.warning("Structured topic detection failed", extra={"error": str(exc)})

    if not columns:
        # Still allow open-world search using the raw question text.
        raw = (question or state.get("question") or "").strip()
        if raw:
            state["dataset_topic"] = raw[:120]
            state["search_queries"] = _build_search_queries(raw, raw)
            return state
        state["dataset_topic"] = "general dataset"
        return state

    lower_columns = " ".join([col.lower() for col in columns])
    best_topic = "general dataset"
    best_matches = 0

    for topic_name, keywords in DATASET_TOPIC_KEYWORDS.items():
        matches = sum(1 for token in keywords if token in lower_columns)
        if matches > best_matches:
            best_matches = matches
            best_topic = f"{topic_name} dataset"

    state["dataset_topic"] = best_topic
    return state
