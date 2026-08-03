"""Phase 3 — LLM-Based Intent Classification.

Supported Intents:
- preview
- eda
- statistics
- visualization
- qa
- forecast
- comparison
- chart_explanation
- dataset_switch
- dataset_search
- general_chat
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.config import settings
from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm

logger = get_logger(__name__)

SUPPORTED_INTENTS = frozenset(
    {
        "preview",
        "eda",
        "statistics",
        "visualization",
        "qa",
        "forecast",
        "comparison",
        "chart_explanation",
        "dataset_switch",
        "dataset_search",
        "general_chat",
    }
)

LEGACY_INTENT_MAP = {
    "statistical_analysis": "statistics",
    "explanation": "chart_explanation",
    "forecasting": "forecast",
    "dataset_autoload": "dataset_switch",
}


def normalize_intent_name(intent: str) -> str:
    cleaned = (intent or "").strip().lower()
    cleaned = LEGACY_INTENT_MAP.get(cleaned, cleaned)
    return cleaned if cleaned in SUPPORTED_INTENTS else "eda"


def classify_intents(question: str) -> list[str]:
    """
    Phase 3 Intent Classification.
    Returns list of standard intents from SUPPORTED_INTENTS.
    """
    q = (question or "").strip()
    if not q:
        return ["eda"]

    lowered = q.lower()

    deterministic = _deterministic_intent_classification(lowered)
    if deterministic:
        return list(dict.fromkeys(deterministic))

    use_llm = bool(getattr(settings, "USE_LLM_INTENT", True))
    if use_llm:
        try:
            llm_intents = _classify_via_llm(q)
            if llm_intents:
                return list(dict.fromkeys(llm_intents))
        except Exception as exc:
            logger.warning("LLM intent classification failed", extra={"error": str(exc)})

    return ["eda"]


def _deterministic_intent_classification(lowered: str) -> list[str]:
    intents = []

    # 1. Preview
    if any(p in lowered for p in ("first ", "head", "tail", "sample rows", "show rows", "list columns", "show columns", "first 5", "first 10")):
        intents.append("preview")

    # 2. EDA
    if any(p in lowered for p in ("missing values", "null values", "nulls", "nans", "duplicates", "describe dataset", "describe data", "summary statistics", "eda", "data summary", "dataset overview", "data profile")):
        intents.append("eda")

    # 3. Statistics
    if any(p in lowered for p in ("average ", "mean ", "median ", "variance", "std dev", "standard deviation", "max ", "maximum ", "min ", "minimum ", "count of", "total fare", "sum of", "quantile")):
        intents.append("statistics")

    # 4. Visualization
    if any(p in lowered for p in ("plot ", "histogram", "correlation matrix", "heatmap", "scatter plot", "bar chart", "pie chart", "box plot", "draw chart", "graph ", "visualize ", "visualise ")):
        intents.append("visualization")

    # 5. Chart Explanation
    if any(p in lowered for p in ("explain this chart", "explain chart", "explain plot", "interpret chart", "what does this graph mean")):
        intents.append("chart_explanation")

    # 6. Forecast
    if any(p in lowered for p in ("forecast", "predict", "projection", "future trend")):
        intents.append("forecast")

    # 7. Comparison
    if any(p in lowered for p in ("compare ", "versus", " vs ", "difference between")):
        intents.append("comparison")

    # 8. Dataset Switch
    if any(p in lowered for p in ("switch to", "load iris", "load dataset", "open file", "import dataset")) or (any(p in lowered for p in ("analyze ", "analyse ")) and not any(p in lowered for p in ("missing", "null", "duplicate", "histogram", "average", "first", "describe", "fare", "age", "chart", "summary"))):
        intents.append("dataset_switch")
        intents.append("eda")

    # 9. Dataset Search
    if any(p in lowered for p in ("search dataset", "find dataset", "download dataset", "search for data", "search data", "find data")) or (lowered.startswith("search ") and not any(p in lowered for p in ("missing", "null", "row", "col", "column", "hist", "plot", "chart", "stat"))):
        intents.append("dataset_search")

    # 10. General Chat
    if lowered in {"hello", "hi", "hey", "help", "who are you", "what can you do"}:
        intents.append("general_chat")

    return [normalize_intent_name(i) for i in intents if i]


def _fallback_intent_classification(lowered: str) -> list[str]:
    """Legacy fallback alias for tests expecting dataset_autoload."""
    intents = _deterministic_intent_classification(lowered.lower() if lowered else "")
    legacy_mapped = []
    for i in intents:
        if i == "dataset_switch":
            legacy_mapped.extend(["dataset_autoload", "dataset_switch"])
        else:
            legacy_mapped.append(i)
    return list(dict.fromkeys(legacy_mapped))


def _classify_via_llm(question: str) -> list[str]:
    prompt = f"""You are an analytics intent classifier.
Classify the question into ONE or MORE supported intents:
- preview
- eda
- statistics
- visualization
- qa
- forecast
- comparison
- chart_explanation
- dataset_switch
- dataset_search
- general_chat

Return ONLY JSON: {{"intents": ["<intent>"]}}

Question: {question}"""

    logger.info("LLM INTENT CLASSIFIER INVOKED", extra={"prompt": question})
    response = invoke_llm(prompt)
    raw = _parse_intents(response)
    return [normalize_intent_name(i) for i in raw if i]


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
