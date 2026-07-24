"""Multi-source open dataset discovery with loadable-file resolution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote_plus

import requests

from backend.config import settings
from backend.core.logger import get_logger
from backend.utils.dataset_resolver import is_loadable_url, prefer_validated

logger = get_logger(__name__)

# Trusted raw downloadable datasets — high-confidence shortcuts for common topics.
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
    "electric vehicle": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/mpg.csv",
    "ev": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/mpg.csv",
    "iris": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv",
    "titanic": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/titanic.csv",
    "tips": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv",
    "housing": "https://raw.githubusercontent.com/plotly/datasets/master/housing.csv",
    # Annual gold prices (USD) — open data, not India GDP.
    "gold": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
    "gold price": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
    "gold rate": "https://raw.githubusercontent.com/datasets/gold-prices/master/data/annual.csv",
}

REQUEST_TIMEOUT = 6

# Tokens that appear in almost every open-data page — ignore for relevance matching.
STOP_TOKENS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "data",
    "dataset",
    "datasets",
    "open",
    "csv",
    "json",
    "file",
    "files",
    "raw",
    "download",
    "public",
    "world",
    "global",
    "analysis",
    "analyze",
    "study",
    "explore",
    "country",
    "countries",
    "by",
    "in",
    "of",
    "to",
    "on",
    "levels",
    "rate",
    "rates",
    "statistics",
    "stats",
    "values",
    "total",
    "annual",
    "yearly",
    "series",
}

CONNECT_SOURCES_HINT = (
    "You can still continue by: "
    "(1) uploading a CSV/Excel/JSON/Parquet file, "
    "(2) pasting a direct download URL to a tabular file, or "
    "(3) connecting an open-data source you already have."
)


def _topic_tokens(text: str) -> list[str]:
    return [
        token
        for token in (text or "").lower().split()
        if len(token) > 2 and token not in STOP_TOKENS
    ]


def dataset_search_agent(state: dict[str, Any]) -> dict[str, Any]:
    """Find the best downloadable dataset for the current topic.

    Strategy:
    1. Trusted registry shortcuts
    2. Live multi-source APIs (HF, CKAN/data.gov, GitHub-ish raw map, catalog)
    3. Resolve landing pages → loadable files + light validation
    4. If nothing loadable: set guidance for upload/URL/connect (never silent fail)
    """
    topic = (state.get("dataset_topic") or state.get("question") or "").strip()
    search_queries = state.get("search_queries") or _build_search_queries(topic)

    # User already connected a loadable source (upload path sets file elsewhere;
    # direct URL may already be on state from topic agent).
    # NEVER keep a stale session URL when rediscovering a new topic (e.g. gold vs GDP).
    existing = state.get("dataset_url")
    if (
        existing
        and is_loadable_url(existing)
        and not state.get("force_reload_dataset")
        and not state.get("topic_mismatch")
    ):
        state["dataset_discovery"] = {
            "status": "provided",
            "source": state.get("source") or "direct_url",
            "url": existing,
            "validated": False,
            "candidates": 1,
            "loadable_candidates": 1,
        }
        state.pop("needs_user_data", None)
        state["stop"] = False
        return state

    if state.get("force_reload_dataset") or state.get("topic_mismatch"):
        state["dataset_url"] = None

    if not topic:
        return _apply_not_found(state, topic="")

    results: list[dict[str, Any]] = []

    # 0) Product memory — datasets the copilot has successfully used before
    #    (ChatGPT-like "remembering", not Ollama weight training).
    try:
        from backend.memory.learned_datasets import recall_datasets

        remembered = recall_datasets(topic, limit=5)
        for item in remembered:
            results.append(
                {
                    "title": item.get("title") or f"Learned: {item.get('topic')}",
                    "description": item.get("description")
                    or f"Previously learned dataset for {item.get('topic')}",
                    "source": "Learned Memory",
                    "url": item.get("url"),
                    "rank_hint": int(item.get("rank_hint") or 22),
                    "loadable": True,
                    "memory_score": item.get("memory_score"),
                }
            )
        if remembered:
            state["learned_hit"] = True
    except Exception as exc:
        logger.warning("Learned memory recall failed", extra={"error": str(exc)})

    # Parallel multi-source discovery for first query + topic.
    queries = list(dict.fromkeys([topic, *search_queries]))[:4]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = []
        for query in queries:
            futures.append(pool.submit(_search_raw_registry, query))
            futures.append(pool.submit(_search_catalog, query))
            futures.append(pool.submit(_search_world_bank, query))
            futures.append(pool.submit(_search_huggingface, query))
            futures.append(pool.submit(_search_data_gov_ckan, query))
            futures.append(pool.submit(_search_github_raw, query))

        for future in as_completed(futures):
            try:
                batch = future.result() or []
                results.extend(batch)
            except Exception as exc:
                logger.warning("Dataset search worker failed", extra={"error": str(exc)})

    results = _dedupe_results(results)

    if not results:
        results = _search_raw_registry(topic, force_partial=True)

    # Resolve HF pages → files; probe top loadable candidates.
    ranked = prefer_validated(results, max_probe=4)
    state["dataset_search_results"] = ranked[:10]
    state["related_datasets"] = ranked[:5]
    state["search_queries"] = search_queries
    state["dataset_topic"] = topic

    loadable = [
        item
        for item in ranked
        if item.get("loadable") and item.get("url") and (item.get("validated") or is_loadable_url(item.get("url")))
    ]

    # Drop loadable candidates with no topical relevance (API noise).
    tokens = _topic_tokens(topic)
    if tokens and loadable:
        relevant = []
        for item in loadable:
            # Learned memory already topic-scored.
            if item.get("source") == "Learned Memory":
                relevant.append(item)
                continue
            text = f"{item.get('title', '')} {item.get('description', '')} {item.get('url', '')}".lower()
            hits = sum(1 for tok in tokens if tok in text)
            # Require at least one distinctive token; prefer multi-token overlap.
            if topic.lower() in text or hits >= 1:
                # Reject registry shortcuts unless their keyword is in the topic.
                if item.get("source") in {"Trusted Open Data", "GitHub", "World Bank"}:
                    if not any(key in topic.lower() for key in RAW_DATASETS):
                        # Still allow if title clearly matches tokens (not bare GDP dump).
                        if hits == 0:
                            continue
                        title_l = (item.get("title") or "").lower()
                        if any(bad in title_l for bad in ("gdp", "population", "inflation")) and not any(
                            bad in topic.lower() for bad in ("gdp", "population", "inflation")
                        ):
                            continue
                relevant.append(item)
        loadable = relevant or []

    if not loadable:
        # Still surface related suggestions even if not auto-loadable.
        return _apply_not_found(state, topic=topic, related=ranked[:5])

    best = _choose_best_dataset(topic, loadable)
    state["dataset_url"] = best["url"]
    state["dataset_source"] = best.get("source")
    state["dataset_discovery"] = {
        "status": "found",
        "source": best.get("source"),
        "title": best.get("title"),
        "url": best.get("url"),
        "validated": bool(best.get("validated")),
        "candidates": len(ranked),
        "loadable_candidates": len(loadable),
    }
    state.pop("needs_user_data", None)
    state.pop("data_acquisition_options", None)

    # Clear prior not-found answer if any.
    if state.get("error_type") == "DATASET_NOT_FOUND":
        state.pop("error", None)
        state["error_type"] = None

    logger.info(
        "Dataset search selected best match",
        extra={
            "action": "dataset_search_agent",
            "topic": topic,
            "url": best.get("url"),
            "source": best.get("source"),
            "candidates": len(ranked),
            "loadable": len(loadable),
        },
    )
    return state


def _apply_not_found(
    state: dict[str, Any],
    topic: str,
    related: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from backend.errors.error_types import DATASET_NOT_FOUND

    topic_label = topic or "this topic"
    message = (
        f'I could not find a downloadable open dataset for "{topic_label}". '
        f"{CONNECT_SOURCES_HINT}"
    )
    if related:
        titles = [str(item.get("title") or item.get("url") or "dataset") for item in related[:3]]
        message += " Related open-data leads (may need a direct file link): " + "; ".join(titles) + "."

    state["answer"] = message
    state["error"] = message
    state["error_type"] = DATASET_NOT_FOUND
    state["needs_user_data"] = True
    state["data_acquisition_options"] = [
        {
            "type": "upload",
            "label": "Upload a CSV, Excel, JSON, or Parquet file",
            "how": "Use the upload endpoint or UI dropzone, then ask your analysis question.",
        },
        {
            "type": "direct_url",
            "label": "Paste a direct download URL",
            "how": "Provide a link ending in .csv / .json / .xlsx / .parquet in your question or as file_path.",
        },
        {
            "type": "connect_source",
            "label": "Connect an external source",
            "how": "Use open portals (data.gov, World Bank, Kaggle, Hugging Face) and paste a raw file URL.",
        },
    ]
    state["dataset_discovery"] = {
        "status": "not_found",
        "topic": topic,
        "candidates": len(related or []),
        "loadable_candidates": 0,
    }
    state["related_datasets"] = related or state.get("related_datasets") or []
    # Stop further analysis nodes that require data; insight can still speak.
    state["stop"] = True

    logger.warning(
        "Dataset search found no loadable results",
        extra={"action": "dataset_search_agent", "topic": topic},
    )
    return state


def _build_search_queries(topic: str) -> list[str]:
    cleaned = (topic or "").strip()
    if not cleaned:
        return []
    queries = [cleaned, f"{cleaned} dataset csv", f"{cleaned} open data"]
    return list(dict.fromkeys(queries))


def _search_raw_registry(topic: str, force_partial: bool = False) -> list[dict[str, Any]]:
    matches = []
    normalized = topic.lower()
    tokens = _topic_tokens(normalized)
    country_tokens = {
        "india",
        "china",
        "japan",
        "germany",
        "brazil",
        "canada",
        "france",
        "australia",
        "united",
        "states",
        "kingdom",
        "usa",
        "uk",
        "us",
    }
    for keyword, url in RAW_DATASETS.items():
        direct = keyword in normalized
        partial = force_partial and any(
            token == keyword or token in keyword.split() or keyword in token
            for token in tokens
        )
        if not (direct or partial):
            continue

        # Avoid weak hits: "video game sales" must not map to generic tips/sales CSV.
        key_parts = set(keyword.split())
        residual = [t for t in tokens if t not in key_parts and t not in country_tokens]
        if residual and direct:
            # Allow only if residual is tiny noise; otherwise require open search.
            if len(residual) >= 1 and keyword in {
                "sales",
                "revenue",
                "stock",
                "energy",
                "student",
                "housing",
            }:
                continue

        matches.append(
            {
                "title": f"Open data CSV for {keyword}",
                "description": f"Downloadable raw CSV covering {keyword}.",
                "source": "Trusted Open Data",
                "url": url,
                "rank_hint": 12 if direct else 6,
            }
        )
    return matches


def _search_catalog(topic: str) -> list[dict[str, Any]]:
    matches = []
    normalized = topic.lower()
    tokens = _topic_tokens(normalized)
    if not tokens:
        return matches

    for dataset in settings.DATASET_CATALOG:
        title = dataset.get("title", "")
        description = dataset.get("description", "")
        combined = f"{title} {description}".lower()
        # Require strong topical overlap (majority of distinctive tokens), not
        # weak hits like "country" matching every World Bank page.
        hits = sum(1 for token in tokens if token in combined)
        if normalized in combined or (tokens and hits >= max(1, (len(tokens) + 1) // 2)):
            url = dataset.get("url", "")
            raw = _raw_url_for_text(" ".join(tokens))
            # Only map to a raw shortcut when a registry key is explicitly in the topic.
            if raw and not any(key in normalized for key in RAW_DATASETS):
                raw = None
            matches.append(
                {
                    "title": title,
                    "description": description,
                    "source": dataset.get("source", "catalog"),
                    "url": raw or url,
                    "rank_hint": 5 if raw else 1,
                }
            )
    return matches


def _search_world_bank(topic: str) -> list[dict[str, Any]]:
    matches = []
    normalized = topic.lower()
    tokens = _topic_tokens(normalized)
    for key, url in settings.DATASET_SOURCES.items():
        # Only when the indicator key itself is requested — not every "by country" ask.
        if key in normalized or key in tokens:
            matches.append(
                {
                    "title": f"World Bank / open {key.upper()} dataset",
                    "description": f"Open dataset for {key}",
                    "source": "World Bank",
                    "url": url,
                    "rank_hint": 10,
                }
            )
    return matches


def _search_github_raw(topic: str) -> list[dict[str, Any]]:
    # Reuse registry gating so "sales" inside a longer topic does not force tips.csv.
    return [
        {
            **item,
            "title": item["title"].replace("Open data CSV", "GitHub CSV dataset"),
            "source": "GitHub",
            "rank_hint": max(1, int(item.get("rank_hint") or 0) - 1),
        }
        for item in _search_raw_registry(topic, force_partial=False)
    ]


def _search_huggingface(topic: str) -> list[dict[str, Any]]:
    search_url = f"https://huggingface.co/api/datasets?search={quote_plus(topic)}&limit=5"
    results = []
    try:
        response = requests.get(search_url, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return results
        records = response.json()
        if not isinstance(records, list):
            return results
        for record in records[:5]:
            repo_id = record.get("id")
            if not repo_id:
                continue
            results.append(
                {
                    "title": record.get("id", "HuggingFace dataset"),
                    "description": str(
                        (record.get("cardData") or {}).get("description")
                        or record.get("description")
                        or ""
                    )[:300],
                    "source": "Hugging Face",
                    "url": f"https://huggingface.co/datasets/{repo_id}",
                    "rank_hint": 4,
                }
            )
    except Exception as exc:
        logger.warning(
            "Hugging Face dataset search failed",
            extra={"topic": topic, "error": str(exc)},
        )
    return results


def _search_data_gov_ckan(topic: str) -> list[dict[str, Any]]:
    """Live CKAN search against catalog.data.gov."""
    results: list[dict[str, Any]] = []
    api_url = (
        "https://catalog.data.gov/api/3/action/package_search"
        f"?q={quote_plus(topic)}&rows=5"
    )
    try:
        response = requests.get(api_url, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return _search_data_gov_fallback(topic)

        payload = response.json()
        packages = (((payload or {}).get("result") or {}).get("results")) or []
        for package in packages[:5]:
            title = package.get("title") or package.get("name") or "data.gov dataset"
            notes = (package.get("notes") or "")[:300]
            resources = package.get("resources") or []
            best_url = None
            rank = 2
            for resource in resources:
                res_url = resource.get("url") or ""
                fmt = (resource.get("format") or "").lower()
                if is_loadable_url(res_url) or fmt in {"csv", "json", "xlsx", "xls", "parquet"}:
                    best_url = res_url
                    rank = 9
                    break
            if not best_url and resources:
                best_url = resources[0].get("url")
            if not best_url:
                continue
            results.append(
                {
                    "title": title,
                    "description": notes,
                    "source": "data.gov",
                    "url": best_url,
                    "rank_hint": rank,
                }
            )
    except Exception as exc:
        logger.warning(
            "data.gov CKAN search failed",
            extra={"topic": topic, "error": str(exc)},
        )
        return _search_data_gov_fallback(topic)

    return results or _search_data_gov_fallback(topic)


def _search_data_gov_fallback(topic: str) -> list[dict[str, Any]]:
    normalized = topic.lower()
    fallback = []
    mapping = {
        "gdp": ("Global GDP by Country", RAW_DATASETS["gdp"]),
        "population": ("World Population by Country", RAW_DATASETS["population"]),
        "inflation": ("Global Inflation Rates", RAW_DATASETS["inflation"]),
    }
    for key, (title, url) in mapping.items():
        if key in normalized:
            fallback.append(
                {
                    "title": title,
                    "description": f"Open data for {key}.",
                    "source": "Data.gov / Open Data",
                    "url": url,
                    "rank_hint": 8,
                }
            )
    return fallback


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
    tokens = _topic_tokens(normalized)

    def score(result: dict[str, Any]) -> int:
        score_value = int(result.get("rank_hint") or 0)
        text = f"{result.get('title', '')} {result.get('description', '')} {result.get('source', '')}".lower()
        if normalized in text:
            score_value += 5
        token_hits = sum(1 for token in tokens if token in text)
        score_value += token_hits * 2
        # Penalize candidates with zero topical overlap (bad multi-source noise).
        if tokens and token_hits == 0 and normalized not in text:
            score_value -= 8
        if result.get("validated"):
            score_value += 10
        if result.get("loadable") or is_loadable_url(result.get("url", "")):
            score_value += 5
        if result.get("source") in {"GitHub", "Trusted Open Data", "World Bank"}:
            score_value += 2
        if "raw.githubusercontent.com" in (result.get("url") or ""):
            score_value += 4
        return score_value

    return max(results, key=score)
