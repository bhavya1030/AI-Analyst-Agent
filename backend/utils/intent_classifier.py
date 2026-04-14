def classify_intents(question: str):

    question = (question or "").lower()

    intents = []

    dataset_keywords = [
        "find dataset",
        "fetch dataset",
        "download dataset",
        "dataset about",
        "get dataset",
    ]

    viz_keywords = [
        "plot",
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

    comparison_topics = [
        "gdp",
        "population",
        "inflation",
    ]

    explain_keywords = [
        "explain",
        "insight",
        "why",
        "interpret",
    ]

    auto_analysis_keywords = [
        "analyze dataset",
        "analyze data",
        "explore dataset",
        "explore data",
        "summarize dataset",
        "summarize data",
        "study dataset"
    ]

    cleaning_keywords = [
        "clean",
        "missing values",
        "null values",
        "drop missing",
        "remove null",
    ]

    if any(k in question for k in dataset_keywords):
        intents.append("dataset_search")

    if any(k in question for k in viz_keywords):
        intents.append("visualization")

    if any(k in question for k in stat_keywords):
        intents.append("statistical_analysis")

    if (any(k in question for k in compare_keywords)
            and any(topic in question for topic in comparison_topics)):
        intents.append("comparison")

    if any(k in question for k in explain_keywords):
        intents.append("explanation")

    if any(k in question for k in auto_analysis_keywords):
        intents.append("auto_analysis")

    if any(k in question for k in cleaning_keywords):
        intents.append("cleaning")

    if not intents:
        intents.append("eda")

    return list(dict.fromkeys(intents))
