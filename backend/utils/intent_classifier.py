import json

from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm

logger = get_logger(__name__)


def classify_intents(question: str):
    question = (question or "").strip()

    if not question:
        return ["eda"]

    prompt = f"""
You are an analytics intent classifier.
Possible intents:
- dataset_search
- dataset_autoload
- visualization
- statistical_analysis
- forecasting
- comparison
- eda
- explanation

Return ONLY JSON:
{{
  "intents": [...]
}}

Input:
{question}
"""

    response = invoke_llm(prompt)
    intents = _parse_intents(response)

    if not intents:
        intents = _fallback_intent_classification(question)

    if not intents:
        return ["eda"]

    return list(dict.fromkeys(intents))


def _parse_intents(response: str) -> list[str]:
    if not response:
        return []

    try:
        payload = json.loads(response)
    except Exception:
        payload = _extract_json(response)
        if payload is None:
            return []

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return []

    if not isinstance(payload, dict):
        return []

    intents = payload.get("intents")
    if not isinstance(intents, list):
        return []

    return [str(intent).strip() for intent in intents if str(intent).strip()]


def _extract_json(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


def _fallback_intent_classification(question: str) -> list[str]:
    normalized = question.lower()
    intents = []

    dataset_keywords = [
        "find dataset",
        "fetch dataset",
        "download dataset",
        "dataset about",
        "get dataset",
        "similar dataset",
    ]

    viz_keywords = [
        "plot",
        "show",
        "display",
        "chart",
        "graph",
        "distribution",
        "scatter",
        "bar",
        "pie",
        "line",
        "box",
        "heatmap",
        "correlation",
        "trend",
        "histogram",
        "vs",
    ]

    stat_keywords = [
        "average",
        "mean",
        "max",
        "min",
        "median",
        "variance",
        "std",
        "sum",
        "count",
    ]

    compare_keywords = [
        "compare",
        "difference",
        "relationship",
    ]

    explain_keywords = [
        "explain",
        "insight",
        "why",
        "interpret",
    ]

    forecasting_keywords = [
        "predict",
        "forecast",
        "future",
        "projection",
        "estimate next",
        "future trend",
        "next years",
        "next year",
        "next 5 years",
        "next 10 years",
        "project future",
    ]

    dataset_topic_keywords = [
        "gdp",
        "population",
        "inflation",
        "climate",
        "temperature",
        "sales",
        "revenue",
        "stock",
        "unemployment",
        "energy",
        "covid",
    ]

    if any(k in normalized for k in dataset_keywords):
        intents.append("dataset_search")

    if any(k in normalized for k in viz_keywords):
        intents.append("visualization")

    if any(k in normalized for k in stat_keywords):
        intents.append("statistical_analysis")

    if any(k in normalized for k in compare_keywords):
        intents.append("comparison")

    if any(k in normalized for k in explain_keywords):
        intents.append("explanation")

    if any(k in normalized for k in forecasting_keywords):
        intents.append("forecasting")

    if any(k in normalized for k in dataset_topic_keywords):
        intents.append("dataset_autoload")

    if not intents:
        intents.append("eda")

    return list(dict.fromkeys(intents))
