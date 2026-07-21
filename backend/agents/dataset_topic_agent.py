import json
import re

from backend.config import settings
from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm

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


def dataset_topic_agent(state):
    question = (state.get("question") or "").strip()

    # Fast deterministic path — critical for product UX latency.
    topic = _extract_topic_from_question(question)
    if topic:
        state["dataset_topic"] = topic
        _extract_focus_entities(state, question)
        logger.info(
            "Dataset topic resolved without LLM",
            extra={"action": "dataset_topic_agent", "dataset_topic": topic},
        )
        return state

    if question and bool(getattr(settings, "USE_LLM_TOPIC", False)):
        prompt = f"""
Extract the dataset topic for data discovery.
Examples:
"Analyze GDP growth" -> GDP
"Analyze India's GDP" -> India GDP
"Study electric vehicle adoption" -> electric vehicle adoption
"Forecast cryptocurrency trends" -> cryptocurrency
"Compare GDP and Population" -> GDP population

Return ONLY:
{{
  "dataset_topic": "..."
}}

Input:
{question}
"""
        try:
            response = invoke_llm(prompt)
            topic = _parse_topic_response(response)
        except Exception as exc:
            logger.warning(
                "Topic LLM extraction failed",
                extra={"error": str(exc)},
            )
            topic = ""

        if topic:
            state["dataset_topic"] = topic
            _extract_focus_entities(state, question)
            return state

    return _fallback_topic(state, question)


def _extract_topic_from_question(question: str) -> str:
    if not question:
        return ""

    normalized = question.lower()
    # Strip common instruction verbs for cleaner topics.
    cleaned = re.sub(
        r"\b(analyze|analyse|analysis|study|explore|investigate|show|plot|"
        r"forecast|predict|compare|visualize|visualise|display|summarize|"
        r"summary|of|the|a|an|for|next|\d+\s*years?)\b",
        " ",
        normalized,
    )
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    metrics = [token for token in METRIC_TOKENS if token in normalized]
    countries = []
    for country in sorted(COUNTRY_HINTS, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(country)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            # Normalize short aliases.
            if country in {"usa", "us"}:
                label = "united states"
            elif country == "uk":
                label = "united kingdom"
            else:
                label = country
            if label not in countries:
                countries.append(label)

    parts = []
    if countries:
        parts.extend(countries)
    if metrics:
        parts.extend(metrics)
    elif cleaned and cleaned not in {"", "data", "dataset"}:
        # Keep a short cleaned phrase when no explicit metric found.
        parts.append(cleaned)

    topic = " ".join(parts).strip()
    if not topic:
        return ""

    # Title-ish for readability while search still lowercases.
    return topic


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


def _parse_topic_response(response: str) -> str:
    if not response:
        return ""

    try:
        payload = json.loads(response)
    except Exception:
        payload = _extract_json(response)
        if payload:
            try:
                payload = json.loads(payload)
            except Exception:
                return ""
        else:
            return ""

    if not isinstance(payload, dict):
        return ""

    topic = payload.get("dataset_topic") or payload.get("topic")
    if isinstance(topic, str):
        return topic.strip()

    return ""


def _extract_json(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


def _fallback_topic(state, question: str = ""):
    topic = _extract_topic_from_question(question or state.get("question") or "")
    if topic:
        state["dataset_topic"] = topic
        _extract_focus_entities(state, question or state.get("question") or "")
        return state

    columns = state.get("columns") or []
    if not columns:
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
