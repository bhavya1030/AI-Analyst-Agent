import json

from backend.config import settings
from backend.core.logger import get_logger
from backend.llm.ollama_client import invoke_llm

logger = get_logger(__name__)


def classify_intents(question: str):
    """Classify analytics intents.

    Product rule: deterministic keyword fallback runs first so the copilot stays
    responsive and predictable. The LLM is only used when the fallback is weak
    (empty or bare "eda") and the question is ambiguous.
    """
    question = (question or "").strip()

    if not question:
        return ["eda"]

    fallback = _fallback_intent_classification(question)
    # Product default: deterministic intents only. Local LLMs can take minutes
    # per call and break the ChatGPT-like UX. Enable opt-in via settings if needed.
    use_llm = bool(getattr(settings, "USE_LLM_INTENT", False))
    specific = [intent for intent in fallback if intent != "eda"]

    if specific or not use_llm:
        return list(dict.fromkeys(fallback or ["eda"]))

    # Opt-in LLM path for ambiguous questions only.
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

    logger.info(
        "LLM INTENT CLASSIFIER INVOKED",
        extra={"prompt": question, "model": settings.OLLAMA_MODEL},
    )
    try:
        response = invoke_llm(prompt)
        intents = _parse_intents(response)
        if intents:
            return list(dict.fromkeys(intents))
    except Exception as exc:
        logger.warning(
            "Intent LLM classification failed; using fallback",
            extra={"error": str(exc)},
        )

    return list(dict.fromkeys(fallback or ["eda"]))


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
        "search for data",
        "find data on",
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
        "visualize",
        "visualise",
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
        "how many",
        "what is the",
    ]

    compare_keywords = [
        "compare",
        "comparison",
        "difference",
        "versus",
        " vs ",
        "relationship between",
    ]

    explain_keywords = [
        "explain",
        "insight",
        "why",
        "interpret",
        "what does",
        "tell me about",
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
        "for the next",
    ]

    analysis_keywords = [
        "analyze",
        "analyse",
        "analysis",
        "explore",
        "investigate",
        "study",
        "overview",
        "summarize",
        "summary",
        "eda",
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
        "electric vehicle",
        "ev sales",
        "co2",
        "emission",
        "housing",
        "literacy",
        "cryptocurrency",
        "bitcoin",
        "oil",
        "agriculture",
        "traffic",
        "crime",
    ]

    if any(k in normalized for k in dataset_keywords):
        intents.append("dataset_search")

    if any(k in normalized for k in compare_keywords):
        intents.append("comparison")

    if any(k in normalized for k in forecasting_keywords):
        intents.append("forecasting")

    if any(k in normalized for k in viz_keywords):
        intents.append("visualization")

    if any(k in normalized for k in stat_keywords):
        intents.append("statistical_analysis")

    if any(k in normalized for k in explain_keywords):
        intents.append("explanation")

    if any(k in normalized for k in analysis_keywords):
        intents.append("eda")

    if any(k in normalized for k in dataset_topic_keywords):
        intents.append("dataset_autoload")

    # Open-world: any "analyze/study/explore X" style ask should trigger discovery
    # even when X is not in the known metric list.
    open_world_triggers = (
        "analyze ",
        "analyse ",
        "study ",
        "explore ",
        "investigate ",
        "dataset about",
        "data on ",
        "data about ",
        "find data",
        "open data",
    )
    if any(trigger in normalized for trigger in open_world_triggers):
        if "dataset_autoload" not in intents:
            intents.append("dataset_autoload")
        if "eda" not in intents:
            intents.append("eda")

    # Direct URL means user connected a source.
    if "http://" in normalized or "https://" in normalized:
        intents.append("dataset_autoload")

    if not intents:
        # Default to exploratory analysis — planner decides discovery vs reuse.
        intents.append("eda")

    return list(dict.fromkeys(intents))
