def classify_intents(question: str):

    question = question.lower()

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
        "vs",
        "difference",
        "relationship",
    ]

    explain_keywords = [
        "explain",
        "insight",
        "why",
        "interpret",
    ]

    if any(k in question for k in dataset_keywords):
        intents.append("dataset_search")

    if any(k in question for k in viz_keywords):
        intents.append("visualization")

    if any(k in question for k in stat_keywords):
        intents.append("statistical_analysis")

    if any(k in question for k in compare_keywords):
        intents.append("comparison")

    if any(k in question for k in explain_keywords):
        intents.append("explanation")

    if not intents:
        intents.append("eda")

    return intents