from backend.utils.intent_classifier import classify_intents

FOLLOW_UP_MAPPINGS = {
    "explain that": "explain {subject}",
    "explain this": "explain {subject}",
    "describe that": "explain {subject}",
    "describe this": "explain {subject}",
    "plot another variable": "plot distribution of {subject}",
    "plot another": "plot distribution of {subject}",
    "show another variable": "plot distribution of {subject}",
    "another chart": "plot distribution of {subject}",
    "compare with previous chart": "compare {subject} with another variable",
    "compare that": "compare {subject} with another variable",
    "compare this": "compare {subject} with another variable",
    "show correlation instead": "show correlation heatmap",
    "forecast instead": "predict next 10 years {subject}",
    "forecast that": "predict next 10 years {subject}",
    "forecast this": "predict next 10 years {subject}",
    "instead correlation": "show correlation heatmap",
}

AMBIGUOUS_PHRASES = set(FOLLOW_UP_MAPPINGS.keys())


def _describe_subject(last_column, last_columns):
    if last_column:
        return last_column
    if last_columns:
        return last_columns[-1]
    return "the dataset"


def conversation_context_agent(state):
    question = (state.get("question") or "").strip()
    if not question:
        return state

    lowered = question.lower()
    last_column = state.get("last_column_used")
    last_columns = state.get("last_columns_used") or []
    subject = _describe_subject(last_column, last_columns)
    resolved = None

    for phrase, template in FOLLOW_UP_MAPPINGS.items():
        if phrase in lowered:
            resolved = template.format(subject=subject)
            break

    if resolved:
        state["question"] = resolved
        lowered = resolved.lower()

    intents = classify_intents(lowered)
    if intents:
        state["last_intent"] = intents[0]

    if "forecasting" in intents or "forecast" in lowered:
        state["last_forecast_target"] = subject

    if "visualization" in intents:
        state["last_operation"] = "visualization"
    elif "explanation" in intents:
        state["last_operation"] = "explain"
    elif "statistical_analysis" in intents:
        state["last_operation"] = "statistical_analysis"
    elif "comparison" in intents:
        state["last_operation"] = "compare"
    elif "eda" in intents or "auto_analysis" in intents:
        state["last_operation"] = "analyze"

    return state
