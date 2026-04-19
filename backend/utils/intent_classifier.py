def classify_intents(question: str):

    question = (question or "").lower()

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
        "study dataset",
        "deeply",
        "deep analysis",
        "analyze deeply",
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

    cleaning_keywords = [
        "clean",
        "missing values",
        "null values",
        "drop missing",
        "remove null",
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
        "covid"
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

    if any(k in question for k in forecasting_keywords):
        intents.append("forecasting")

    if any(k in question for k in cleaning_keywords):
        intents.append("cleaning")

    if any(k in question for k in dataset_topic_keywords):
        intents.append("dataset_autoload")

    if not intents:
        intents.append("eda")

    return list(dict.fromkeys(intents))
