from typing import List

DATASET_CATALOG = [
    {
        "title": "World Bank GDP by Country",
        "description": "Annual GDP values for countries from World Bank datasets, suitable for trend and growth analysis.",
        "source": "World Bank",
        "url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
    },
    {
        "title": "World Bank Population by Country",
        "description": "Country-level population totals for demographic and growth analyses.",
        "source": "World Bank",
        "url": "https://data.worldbank.org/indicator/SP.POP.TOTL",
    },
    {
        "title": "US GDP Components Dataset",
        "description": "Gross domestic product breakdown by expenditure components from Data.gov.",
        "source": "Data.gov",
        "url": "https://catalog.data.gov/dataset/us-gdp-components",
    },
    {
        "title": "Global Inflation Rates",
        "description": "Inflation statistics for countries worldwide, useful for macroeconomic comparisons.",
        "source": "Data.gov",
        "url": "https://catalog.data.gov/dataset/global-inflation-rates",
    },
    {
        "title": "GitHub Public CSV of GDP Growth",
        "description": "Community-maintained CSV repository with GDP growth metrics and country-level historical values.",
        "source": "GitHub",
        "url": "https://github.com/datasets/gdp",
    },
    {
        "title": "GitHub CSV of India GDP Growth",
        "description": "Country-specific GDP growth dataset for India sourced from open data repositories.",
        "source": "GitHub",
        "url": "https://github.com/datasets/gdp/tree/main/data",
    },
]


def _score_query(query: str, text: str) -> int:
    query_tokens = [token for token in query.lower().split() if len(token) > 2]
    text_lower = text.lower()
    return sum(1 for token in query_tokens if token in text_lower)


def dataset_embedding_search_agent(state):
    question = (state.get("question") or "").lower()
    if not question:
        state["related_datasets"] = []
        return state

    scored = []
    for dataset in DATASET_CATALOG:
        score = _score_query(question, " ".join([dataset["title"], dataset["description"], dataset["source"]]))
        if score > 0:
            scored.append((score, dataset))

    if not scored:
        scored = [(
            _score_query(question, " ".join([dataset["title"], dataset["description"], dataset["source"]])),
            dataset,
        ) for dataset in DATASET_CATALOG]

    scored.sort(key=lambda item: item[0], reverse=True)
    state["related_datasets"] = [dataset for _, dataset in scored[:4]]
    return state
