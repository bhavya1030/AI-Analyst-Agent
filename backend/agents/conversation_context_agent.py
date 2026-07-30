import re

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
    "show correlation instead": "show correlation heatmap for {subject}",
    "show correlation": "show correlation heatmap for {subject}",
    "show histogram": "show histogram of {subject}",
    "forecast instead": "forecast {subject} for next 10 years",
    "forecast that": "forecast {subject} for next 10 years",
    "forecast this": "forecast {subject} for next 10 years",
    "forecast it": "forecast {subject} for next 10 years",
    "predict it": "forecast {subject} for next 10 years",
    "instead correlation": "show correlation heatmap for {subject}",
    "analyze it": "analyze {subject}",
    "visualize it": "visualize trend of {subject}",
    "plot it": "plot trend of {subject}",
    "show it": "show trend of {subject}",
}

# Exact short follow-ups only (avoid rewriting "forecast gold prices")
EXACT_FOLLOW_UPS = {
    "histogram": "show histogram of {subject}",
    "show histogram": "show histogram of {subject}",
    "correlation": "show correlation heatmap for {subject}",
    "forecast": "forecast {subject} for next 10 years",
    "predict": "forecast {subject} for next 10 years",
}

AMBIGUOUS_PHRASES = set(FOLLOW_UP_MAPPINGS.keys())

PRONOUN_PATTERN = re.compile(
    r"\b(it|that|this|them|those|the same|the data|the dataset)\b",
    re.IGNORECASE,
)


def _describe_subject(state):
    topic = (state.get("dataset_topic") or "").strip()
    if topic and topic.lower() not in {"general dataset", "dataset discovery"}:
        return topic

    last_column = state.get("last_column_used")
    if last_column:
        return str(last_column)

    last_columns = state.get("last_columns_used") or []
    if last_columns:
        return str(last_columns[-1])

    if state.get("data") is not None:
        return "the active dataset"

    return "the dataset"


def _is_follow_up(question: str) -> bool:
    lowered = question.lower().strip()
    if lowered in AMBIGUOUS_PHRASES:
        return True
    if any(phrase in lowered for phrase in FOLLOW_UP_MAPPINGS):
        return True
    # Short pronoun-heavy follow-ups: "forecast it for 10 years"
    if PRONOUN_PATTERN.search(lowered) and len(lowered.split()) <= 12:
        return True
    return False


def _resolve_pronouns(question: str, subject: str) -> str:
    if not subject or subject == "the dataset":
        return question

    def _replace(match):
        token = match.group(0).lower()
        if token in {"the data", "the dataset", "the same"}:
            return subject
        return subject

    # Prefer explicit mappings first; this handles residual pronouns.
    return PRONOUN_PATTERN.sub(_replace, question)


def conversation_context_agent(state):
    question = (state.get("question") or "").strip()
    if not question:
        return state

    # Preserve session continuity markers for downstream agents.
    if state.get("data") is not None:
        state["has_active_dataset"] = True
        if not state.get("topic_mismatch"):
            state["reuse_active_dataset"] = True
            state["planner_skip_upload"] = True
            state["needs_user_data"] = False
    if state.get("dataset_url") and not state.get("dataset_topic"):
        state["dataset_topic"] = state.get("dataset_topic") or "active session dataset"

    # Memory v2: bind topic from session_memory when follow-up has no topic
    try:
        from backend.memory.continuity import is_follow_up_question

        if is_follow_up_question(question) and not state.get("topic_mismatch"):
            sm = state.get("session_memory") or {}
            if isinstance(sm, dict) and sm.get("dataset_topic") and not state.get("dataset_topic"):
                state["dataset_topic"] = sm.get("dataset_topic")
            state["reuse_active_dataset"] = bool(
                state.get("data") is not None
                or state.get("file_path")
                or state.get("dataset_url")
            )
    except Exception:
        pass
    # Phase 5: prefer L2 session memory / L3 dataset hints when subject is weak
    session_mem = state.get("session_memory") or {}
    if isinstance(session_mem, dict):
        if not state.get("last_column_used") and session_mem.get("last_column"):
            state["last_column_used"] = session_mem.get("last_column")
        if not state.get("last_columns_used") and session_mem.get("last_columns"):
            state["last_columns_used"] = list(session_mem.get("last_columns") or [])
        if not state.get("dataset_topic") and session_mem.get("dataset_topic"):
            if not state.get("topic_mismatch"):
                state["dataset_topic"] = session_mem.get("dataset_topic")

    lowered = question.lower()
    subject = _describe_subject(state)
    # Enrich subject from conversation memory summary when generic
    if subject in {"the dataset", "the active dataset"}:
        summary = (state.get("conversation_summary") or "").strip()
        topic = (state.get("dataset_topic") or session_mem.get("dataset_topic") or "").strip()
        if topic:
            subject = topic
        elif summary:
            subject = summary[:80]

    resolved = None

    if lowered.strip() in EXACT_FOLLOW_UPS:
        resolved = EXACT_FOLLOW_UPS[lowered.strip()].format(subject=subject)
    else:
        for phrase, template in FOLLOW_UP_MAPPINGS.items():
            if phrase in lowered:
                resolved = template.format(subject=subject)
                break

    # "compare with China" — keep subject dataset, attach entity
    if resolved is None and re.search(r"\bcompare\s+with\b", lowered):
        rest = re.sub(r"^.*compare\s+with\s+", "", lowered).strip()
        if rest and subject not in {"the dataset", "the active dataset"}:
            resolved = f"compare {subject} with {rest}"

    if resolved is None and _is_follow_up(question):
        resolved = _resolve_pronouns(question, subject)

    if resolved and resolved != question:
        state["question"] = resolved
        state["resolved_from_context"] = True
        state["context_subject"] = subject
        lowered = resolved.lower()
    else:
        state["resolved_from_context"] = False

    # Prefer fast rule-based intents; classify_intents already does fallback-first.
    intents = classify_intents(state.get("question") or lowered)
    if intents:
        state["last_intent"] = intents[0]
        state["intents"] = intents

    if "forecasting" in intents or "forecast" in lowered or "predict" in lowered:
        state["last_forecast_target"] = subject
        state["last_operation"] = "forecast"
    elif "visualization" in intents:
        state["last_operation"] = "visualization"
    elif "comparison" in intents:
        state["last_operation"] = "compare"
    elif "explanation" in intents:
        state["last_operation"] = "explain"
    elif "statistical_analysis" in intents:
        state["last_operation"] = "statistical_analysis"
    elif "eda" in intents or "dataset_autoload" in intents:
        state["last_operation"] = "analyze"

    # When a follow-up arrives and a dataset is already loaded, avoid rediscovery
    # unless the user explicitly asks for a new topic/dataset.
    if state.get("data") is not None and state.get("resolved_from_context"):
        if _question_matches_active_topic(state.get("question") or "", state.get("dataset_topic") or ""):
            state["reuse_active_dataset"] = True
        else:
            # e.g. active topic is India GDP but user now asks about gold.
            state["reuse_active_dataset"] = False
            state["topic_mismatch"] = True

    # Explicit new subject while another dataset is active (not a pronoun follow-up).
    if (
        state.get("data") is not None
        and not state.get("reuse_active_dataset")
        and not state.get("resolved_from_context")
        and _is_new_topic_request(state.get("question") or "", state.get("dataset_topic") or "")
    ):
        state["topic_mismatch"] = True
        state["reuse_active_dataset"] = False

    return state


def _normalize_tokens(text: str) -> set[str]:
    import re

    stop = {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by",
        "analyze", "analyse", "analysis", "study", "explore", "forecast", "predict",
        "next", "previous", "past", "last", "years", "year", "rate", "rates",
        "price", "prices", "data", "dataset", "show", "plot", "trend", "trends",
    }
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in tokens if len(t) > 2 and t not in stop}


def _question_matches_active_topic(question: str, active_topic: str) -> bool:
    """True when the question still refers to the already-loaded dataset."""
    q_tokens = _normalize_tokens(question)
    t_tokens = _normalize_tokens(active_topic)
    if not q_tokens or not t_tokens:
        return True  # pronoun follow-ups often have no topic tokens left
    overlap = q_tokens & t_tokens
    # Enough shared substance, or question only has generic analysis words.
    if overlap:
        return True
    return False


def _is_new_topic_request(question: str, active_topic: str) -> bool:
    """True when the user named a concrete subject different from the active set."""
    q_tokens = _normalize_tokens(question)
    t_tokens = _normalize_tokens(active_topic)
    if not q_tokens:
        return False
    if not t_tokens:
        return True
    return len(q_tokens & t_tokens) == 0
