def recommendation_agent(state):
    """Suggest natural follow-up analyses — ChatGPT-like next questions."""

    profile = state.get("dataset_profile") or {}
    recommendations = []

    numeric_cols = profile.get("numeric_columns", []) or []
    categorical_cols = profile.get("categorical_columns", []) or []
    time_cols = profile.get("time_columns", []) or []
    topic = (state.get("dataset_topic") or "").strip()
    focus = state.get("focus_country")
    operation = (state.get("last_operation") or "").lower()
    question = (state.get("question") or "").lower()

    # When discovery failed, guide acquisition paths instead of fake analysis.
    if state.get("needs_user_data") or state.get("data") is None:
        recommendations.extend(
            [
                "Upload a CSV/Excel/JSON/Parquet file",
                "Paste a direct download URL to a tabular file",
                "Try a public topic (e.g. Analyze world GDP)",
                "Search open data portals and paste a raw file link",
            ]
        )
        state["recommended_next_steps"] = list(dict.fromkeys(recommendations))[:6]
        return state

    # Context-aware conversational suggestions
    if time_cols and numeric_cols:
        target = focus or topic or numeric_cols[0]
        if "forecast" not in operation and "forecast" not in question:
            recommendations.append(f"Forecast {target} for the next 10 years")
        recommendations.append(f"Show the long-term trend for {target}")

    if focus and "gdp" in (topic + " " + question).lower():
        recommendations.append(f"Compare GDP of {focus} with United States")
        if focus.lower() != "india":
            recommendations.append(f"Compare GDP of {focus} with India")
        else:
            recommendations.append("Compare GDP of India with China")

    if "population" not in (topic + " " + question).lower() and "gdp" in (topic + " " + question).lower():
        recommendations.append("Compare GDP and Population")

    if len(numeric_cols) >= 2:
        recommendations.append("Generate a correlation heatmap between numeric variables")

    if len(numeric_cols) >= 1 and not time_cols:
        recommendations.append(f"Plot the distribution of {numeric_cols[0]}")

    if len(time_cols) >= 1:
        recommendations.append(f"Run deeper trend analysis over {time_cols[0]}")

    if len(categorical_cols) >= 1 and not focus:
        recommendations.append(f"Compare values across {categorical_cols[0]}")

    if state.get("chart") or state.get("charts"):
        recommendations.append("Explain the chart in more detail")

    if state.get("forecast"):
        recommendations.append("Compare this forecast against a related indicator")

    # Deduplicate while preserving order
    deduped = []
    for item in recommendations:
        if item not in deduped:
            deduped.append(item)

    state["recommended_next_steps"] = deduped[:6]
    return state
