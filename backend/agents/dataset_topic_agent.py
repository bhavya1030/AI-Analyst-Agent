DATASET_TOPIC_KEYWORDS = {
    "macroeconomic": ["gdp", "inflation", "employment", "unemployment", "population", "income", "economic"],
    "climate": ["co2", "temperature", "rain", "climate", "emissions", "carbon", "weather"],
    "education": ["student", "school", "education", "literacy", "test", "score", "grade"],
    "demographic": ["population", "age", "gender", "birth", "mortality", "ethnicity", "race"],
    "financial": ["revenue", "profit", "sales", "expense", "cost", "price", "stock"],
    "health": ["health", "disease", "hospital", "mortality", "covid", "vaccination"],
}


def dataset_topic_agent(state):
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
