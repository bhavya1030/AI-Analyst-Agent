import json

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


def dataset_topic_agent(state):
    question = (state.get("question") or "").strip()

    if not question:
        return _fallback_topic(state)

    prompt = f"""
Extract the dataset topic.
Examples:
"Analyze GDP growth" -> GDP
"Study electric vehicle adoption" -> electric vehicle adoption
"Forecast cryptocurrency trends" -> cryptocurrency

Return ONLY:
{{
  "dataset_topic": "..."
}}

Input:
{question}
"""

    response = invoke_llm(prompt)
    topic = _parse_topic_response(response)

    if not topic:
        return _fallback_topic(state)

    state["dataset_topic"] = topic
    return state


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


def _fallback_topic(state):
    columns = state.get("columns") or []
    if not columns:
        state["dataset_topic"] = "general dataset"
        return state

    lower_columns = " ".join([col.lower() for col in columns])
    best_topic = "general dataset"
    best_matches = 0

    for topic, keywords in DATASET_TOPIC_KEYWORDS.items():
        matches = sum(1 for token in keywords if token in lower_columns)
        if matches > best_matches:
            best_matches = matches
            best_topic = f"{topic} dataset"

    state["dataset_topic"] = best_topic
    return state
