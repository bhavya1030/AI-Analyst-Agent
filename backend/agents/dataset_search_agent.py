import json
from urllib.parse import quote_plus
from typing import Any

import requests

from backend.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

RAW_DATASETS = {
    "gdp": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
    "population": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
    "inflation": "https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv",
    "unemployment": "https://raw.githubusercontent.com/datasets/unemployment/master/data/unemployment.csv",
    "climate": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
    "temperature": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
    "co2": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/global.csv",
    "covid": "https://raw.githubusercontent.com/datasets/covid-19/master/data/countries-aggregated.csv",
    "sales": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv",
    "revenue": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv",
    "stock": "https://raw.githubusercontent.com/datasets/stock-prices/master/data/stock-prices.csv",
    "energy": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/global.csv",
    "student": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/exercise.csv",
}


def dataset_search_agent(state: dict[str, Any]) -> dict[str, Any]:
    topic = (state.get("dataset_topic") or "").strip()
    if not topic:
        state["answer"] = "I could not locate a suitable dataset for this topic."
        return state

    results = []
    results.extend(_search_catalog(topic))
    results.extend(_search_github(topic))
    results.extend(_search_world_bank(topic))
    results.extend(_search_data_gov(topic))
    results.extend(_search_huggingface(topic))

    results = _dedupe_results(results)

    if not results:
        state["answer"] = "I could not locate a suitable dataset for this topic."
        return state

    best = _choose_best_dataset(topic, results)
    state["dataset_search_results"] = results
    state["dataset_url"] = best["url"]
    state["dataset_topic"] = topic
    return state


def _search_catalog(topic: str) -> list[dict[str, Any]]:
    matches = []
    normalized = topic.lower()
    for dataset in settings.DATASET_CATALOG:
        title = dataset.get("title", "")
        description = dataset.get("description", "")
        combined = f"{title} {description}".lower()
        if normalized in combined or any(token in combined for token in normalized.split()):
            matches.append(
                {
                    "title": title,
                    "description": description,
                    "source": dataset.get("source", "catalog"),
                    "url": dataset.get("url", ""),
                }
            )
    return matches


def _search_world_bank(topic: str) -> list[dict[str, Any]]:
    matches = []
    normalized = topic.lower()
    for key, url in settings.DATASET_SOURCES.items():
        if key in normalized or normalized in key:
            matches.append(
                {
                    "title": f"World Bank {key.upper()} dataset",
                    "description": f"World Bank dataset for {key}",
                    "source": "World Bank",
                    "url": url,
                }
            )
    return matches


def _search_data_gov(topic: str) -> list[dict[str, Any]]:
    normalized = topic.lower()
    fallback = []
    if "gdp" in normalized:
        fallback.append(
            {
                "title": "US GDP Components Dataset",
                "description": "Gross domestic product components from Data.gov.",
                "source": "Data.gov",
                "url": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
            }
        )
    if "population" in normalized:
        fallback.append(
            {
                "title": "World Bank Population by Country",
                "description": "Country population totals and growth trends.",
                "source": "Data.gov",
                "url": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
            }
        )
    if "inflation" in normalized:
        fallback.append(
            {
                "title": "Global Inflation Rates",
                "description": "International CPI inflation statistics.",
                "source": "Data.gov",
                "url": "https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv",
            }
        )
    return fallback


def _search_github(topic: str) -> list[dict[str, Any]]:
    normalized = topic.lower()
    results = []
    for keyword, url in RAW_DATASETS.items():
        if keyword in normalized or normalized in keyword:
            results.append(
                {
                    "title": f"GitHub CSV dataset for {keyword}",
                    "description": f"Raw CSV dataset for {keyword} from GitHub.",
                    "source": "GitHub",
                    "url": url,
                }
            )
    return results


def _search_huggingface(topic: str) -> list[dict[str, Any]]:
    normalized = topic.lower()
    search_url = f"https://huggingface.co/api/datasets?search={quote_plus(topic)}"
    results = []
    try:
        response = requests.get(search_url, timeout=8)
        if response.status_code == 200:
            records = response.json()
            for record in records[:3]:
                repo_id = record.get("id")
                if repo_id:
                    results.append(
                        {
                            "title": record.get("id", "HuggingFace dataset"),
                            "description": record.get("cardData", {}).get("description", ""),
                            "source": "Hugging Face",
                            "url": f"https://huggingface.co/datasets/{repo_id}",
                        }
                    )
    except Exception as exc:
        logger.warning(
            "Hugging Face dataset search failed",
            extra={"topic": topic, "error": str(exc)},
        )
    return results


def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for result in results:
        key = (result.get("title"), result.get("url"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def _choose_best_dataset(topic: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = topic.lower()
    supported = [result for result in results if _is_supported_url(result.get("url", ""))]
    candidates = supported or results
    def score(result: dict[str, Any]) -> int:
        score_value = 0
        text = f"{result.get('title', '')} {result.get('description', '')} {result.get('source', '')}".lower()
        if normalized in text:
            score_value += 5
        for token in normalized.split():
            if token in text:
                score_value += 1
        if result.get("source") == "GitHub":
            score_value += 1
        if _is_supported_url(result.get("url", "")):
            score_value += 2
        return score_value
    return max(candidates, key=score)


def _is_supported_url(url: str) -> bool:
    lower_url = url.lower()
    return any(lower_url.endswith(ext) for ext in [".csv", ".json", ".xlsx", ".xls", ".parquet"])
