from typing import List

from backend.config import settings

DATASET_CATALOG = settings.DATASET_CATALOG


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
