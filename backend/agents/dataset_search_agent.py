import json
from urllib.parse import quote_plus
from typing import Any

import requests

from backend.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

# Trusted raw downloadable datasets. Dataset Search's job is discovery —
# these keys guarantee the Data Engineer receives a loadable URL.
RAW_DATASETS = {
    "gdp": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
    "population": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
    "inflation": "https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv",
    "unemployment": "https://raw.githubusercontent.com/datasets/unemployment/master/data/unemployment.csv",
    "climate": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
    "temperature": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
    "co2": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/global.csv",
    "emission": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/global.csv",
    "covid": "https://raw.githubusercontent.com/datasets/covid-19/master/data/countries-aggregated.csv",
    "sales": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv",
    "revenue": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv",
    "stock": "https://raw.githubusercontent.com/datasets/s-and-p-500/master/data/data.csv",
    "energy": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/global.csv",
    "student": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/exercise.csv",
    # EV topics map to a general automotive/sales open CSV until a dedicated
    # EV raw feed is pinned; search still ranks topic text for the user.
    "electric vehicle": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/mpg.csv",
    "ev": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/mpg.csv",
}


def dataset_search_agent(state: dict[str, Any]) -> dict[str, Any]:
    """Find the best downloadable dataset for the current topic.

    Does not clean or analyze data — only discovery + ranking.
    """
    topic = (state.get("dataset_topic") or state.get("question") or "").strip()
    if not topic:
        state["answer"] = "I could not locate a suitable dataset for this topic."
        return state

    results: list[dict[str, Any]] = []
    results.extend(_search_raw_registry(topic))
    results.extend(_search_catalog(topic))
    results.extend(_search_github(topic))
    results.extend(_search_world_bank(topic))
    results.extend(_search_data_gov(topic))
    results.extend(_search_huggingface(topic))

    results = _dedupe_results(results)

    if not results:
        # Last-resort keyword map so the product never dead-ends on common topics.
        results = _search_raw_registry(topic, force_partial=True)

    if not results:
        state["answer"] = "I could not locate a suitable dataset for this topic."
        logger.warning(
            "Dataset search found no results",
            extra={"action": "dataset_search_agent", "topic": topic},
        )
        return state

    best = _choose_best_dataset(topic, results)
    state["dataset_search_results"] = results[:10]
    state["related_datasets"] = results[:5]
    state["dataset_url"] = best["url"]
    state["dataset_topic"] = topic
    state["dataset_source"] = best.get("source")

    logger.info(
        "Dataset search selected best match",
        extra={
            "action": "dataset_search_agent",
            "topic": topic,
            "url": best.get("url"),
            "source": best.get("source"),
            "candidates": len(results),
        },
    )
    return state


def _search_raw_registry(topic: str, force_partial: bool = False) -> list[dict[str, Any]]:
    matches = []
    normalized = topic.lower()
    for keyword, url in RAW_DATASETS.items():
        if keyword in normalized or (force_partial and any(token in keyword for token in normalized.split())):
            matches.append(
                {
                    "title": f"Open data CSV for {keyword}",
                    "description": f"Downloadable raw CSV covering {keyword}.",
                    "source": "Trusted Open Data",
                    "url": url,
                    "rank_hint": 10,
                }
            )
    return matches


def _search_catalog(topic: str) -> list[dict[str, Any]]:
    matches = []
    normalized = topic.lower()
    for dataset in settings.DATASET_CATALOG:
        title = dataset.get("title", "")
        description = dataset.get("description", "")
        combined = f"{title} {description}".lower()
        if normalized in combined or any(token in combined for token in normalized.split() if len(token) > 2):
            url = dataset.get("url", "")
            # Prefer mapped raw URL when catalog points at a landing page.
            raw = _raw_url_for_text(combined + " " + normalized)
            matches.append(
                {
                    "title": title,
                    "description": description,
                    "source": dataset.get("source", "catalog"),
                    "url": raw or url,
                    "rank_hint": 4 if raw else 1,
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
                    "rank_hint": 8,
                }
            )
    return matches


def _search_data_gov(topic: str) -> list[dict[str, Any]]:
    normalized = topic.lower()
    fallback = []
    if "gdp" in normalized:
        fallback.append(
            {
                "title": "Global GDP by Country",
                "description": "Country-level GDP series suitable for trend analysis.",
                "source": "Data.gov / Open Data",
                "url": RAW_DATASETS["gdp"],
                "rank_hint": 7,
            }
        )
    if "population" in normalized:
        fallback.append(
            {
                "title": "World Population by Country",
                "description": "Country population totals and growth trends.",
                "source": "Data.gov / Open Data",
                "url": RAW_DATASETS["population"],
                "rank_hint": 7,
            }
        )
    if "inflation" in normalized:
        fallback.append(
            {
                "title": "Global Inflation Rates",
                "description": "International CPI inflation statistics.",
                "source": "Data.gov / Open Data",
                "url": RAW_DATASETS["inflation"],
                "rank_hint": 7,
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
                    "rank_hint": 9,
                }
            )
    return results


def _search_huggingface(topic: str) -> list[dict[str, Any]]:
    search_url = f"https://huggingface.co/api/datasets?search={quote_plus(topic)}"
    results = []
    try:
        response = requests.get(search_url, timeout=5)
        if response.status_code == 200:
            records = response.json()
            for record in records[:3]:
                repo_id = record.get("id")
                if repo_id:
                    results.append(
                        {
                            "title": record.get("id", "HuggingFace dataset"),
                            "description": str(
                                record.get("cardData", {}).get("description", "")
                            )[:300],
                            "source": "Hugging Face",
                            # Landing page — lower rank; engineer needs raw files.
                            "url": f"https://huggingface.co/datasets/{repo_id}",
                            "rank_hint": 0,
                        }
                    )
    except Exception as exc:
        logger.warning(
            "Hugging Face dataset search failed",
            extra={"topic": topic, "error": str(exc)},
        )
    return results


def _raw_url_for_text(text: str) -> str | None:
    normalized = text.lower()
    for key, url in RAW_DATASETS.items():
        if key in normalized:
            return url
    return None


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
        score_value = int(result.get("rank_hint") or 0)
        text = f"{result.get('title', '')} {result.get('description', '')} {result.get('source', '')}".lower()
        if normalized in text:
            score_value += 5
        for token in normalized.split():
            if len(token) > 2 and token in text:
                score_value += 1
        if result.get("source") in {"GitHub", "Trusted Open Data", "World Bank"}:
            score_value += 2
        if _is_supported_url(result.get("url", "")):
            score_value += 5
        else:
            score_value -= 5
        # Prefer raw.githubusercontent.com
        if "raw.githubusercontent.com" in (result.get("url") or ""):
            score_value += 4
        return score_value

    return max(candidates, key=score)


def _is_supported_url(url: str) -> bool:
    if not url:
        return False
    lower_url = url.lower().split("?")[0]
    if any(lower_url.endswith(ext) for ext in [".csv", ".json", ".xlsx", ".xls", ".parquet"]):
        return True
    # Some open-data URLs encode extensions mid-path.
    return any(ext in lower_url for ext in [".csv", ".json", ".parquet"])
