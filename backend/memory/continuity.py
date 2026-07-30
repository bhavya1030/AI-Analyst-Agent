"""Conversation Memory v2 — continuity helpers.

Detect follow-up analysis operations vs true topic changes so the planner
reuses the session dataset instead of asking for upload again.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Tokens that describe *what to do* with data, not *which dataset*.
OPERATION_TOKENS = frozenset(
    {
        "show", "plot", "chart", "graph", "visualize", "visualise", "draw",
        "histogram", "hist", "bar", "line", "scatter", "box", "heatmap",
        "correlation", "correlate", "corr", "distribution", "density",
        "forecast", "predict", "projection", "trend", "trends",
        "compare", "comparison", "versus", "vs",
        "analyze", "analyse", "analysis", "summarize", "summarise", "summary",
        "describe", "explain", "insight", "insights", "eda",
        "mean", "median", "std", "average", "max", "min", "count",
        "filter", "group", "by", "top", "bottom", "rank",
        "again", "another", "same", "more", "please", "help",
        "next", "previous", "past", "last", "years", "year", "months",
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with",
        "from", "it", "this", "that", "them", "those", "data", "dataset",
        "column", "columns", "variable", "variables", "value", "values",
        "using", "use", "make", "create", "generate", "give", "display",
        "rate", "rates", "price", "prices", "over", "time", "series",
    }
)

FOLLOW_UP_PHRASES = (
    "show histogram",
    "histogram",
    "show correlation",
    "correlation",
    "heatmap",
    "forecast",
    "predict",
    "forecast it",
    "predict it",
    "compare with",
    "compare to",
    "vs ",
    "versus",
    "plot it",
    "show it",
    "analyze it",
    "visualise it",
    "visualize it",
    "same dataset",
    "this data",
    "the data",
    "again",
    "another chart",
    "distribution",
)

PRONOUN_RE = re.compile(
    r"\b(it|that|this|them|those|the same|the data|the dataset)\b",
    re.IGNORECASE,
)


def tokenize_content(text: str | None) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 2 and t not in OPERATION_TOKENS
    }


def is_follow_up_question(question: str | None) -> bool:
    """True for operation-only / pronoun follow-ups that keep the active dataset."""
    q = (question or "").strip().lower()
    if not q:
        return False
    if any(p in q for p in FOLLOW_UP_PHRASES):
        # Still a follow-up even if also names a country for compare-with
        return True
    if PRONOUN_RE.search(q) and len(q.split()) <= 14:
        return True
    # Short questions with only operation tokens
    content = tokenize_content(q)
    if not content and len(q.split()) <= 8:
        return True
    return False


def is_new_dataset_topic(
    question: str | None,
    active_topic: str | None,
    *,
    has_active_dataset: bool = False,
) -> bool:
    """
    True when the user names a *different dataset subject* than the session.

    Follow-ups like "show histogram", "forecast", "correlation" return False
    so we keep the bound dataset.
    """
    if not question or not question.strip():
        return False

    # Explicit follow-up / operation → keep session dataset
    if has_active_dataset and is_follow_up_question(question):
        # Exception: "analyze gold" while session is GDP — content tokens differ
        q_content = tokenize_content(question)
        t_content = tokenize_content(active_topic)
        if not t_content:
            # Follow-up with no prior topic name still reuses data if bound
            return False
        if not q_content:
            return False
        # "compare with China" adds country but keeps metric topic
        if q_content & t_content:
            return False
        # Pure follow-up phrases with extra country words (compare with China)
        lowered = question.lower()
        if any(
            p in lowered
            for p in (
                "compare with",
                "compare to",
                " vs ",
                "versus",
                "histogram",
                "correlation",
                "heatmap",
                "forecast",
                "predict",
                "distribution",
                "scatter",
            )
        ):
            return False
        # Distinct subject nouns with open-world analyze verbs → new topic
        if any(
            v in lowered
            for v in ("analyze ", "analyse ", "study ", "explore ", "dataset about")
        ):
            return True
        # Default for content-only questions with no topic overlap
        return True

    q_tokens = tokenize_content(question)
    t_tokens = tokenize_content(active_topic)
    if not q_tokens:
        return False
    if not t_tokens:
        # Session has data path but no topic label — only new if question looks like discovery
        lowered = (question or "").lower()
        if has_active_dataset and is_follow_up_question(question):
            return False
        if has_active_dataset and not any(
            p in lowered for p in ("analyze ", "analyse ", "study ", "explore ", "find data")
        ):
            return False
        return bool(q_tokens)
    return len(q_tokens & t_tokens) == 0


def should_reuse_session_dataset(
    *,
    question: str | None,
    dataset_topic: str | None,
    dataset_path: str | None,
    dataset_url: str | None,
    has_frame: bool,
    file_path_override: str | None = None,
) -> tuple[bool, bool]:
    """
    Returns (reuse, topic_mismatch).

    reuse=True → inject path/frame and skip discovery/upload.
    """
    if file_path_override:
        return False, False

    has_binding = bool(dataset_path or dataset_url or has_frame)
    if not has_binding:
        return False, False

    mismatch = is_new_dataset_topic(
        question,
        dataset_topic,
        has_active_dataset=has_binding,
    )
    if mismatch:
        return False, True
    return True, False


def build_planner_injection(state: dict[str, Any]) -> dict[str, Any]:
    """
    Fields the planner must see so it never asks for upload when data is bound.
    """
    has_data = state.get("data") is not None
    path = state.get("local_path") or state.get("file_path") or state.get("dataset_path")
    url = state.get("dataset_url")
    bound = has_data or bool(path) or bool(url)
    out = {
        "has_active_dataset": bound,
        "reuse_active_dataset": bool(
            bound and not state.get("topic_mismatch") and not state.get("force_reload_dataset")
        ),
        "session_dataset_bound": bound,
        "planner_skip_upload": bound and not state.get("topic_mismatch"),
    }
    if bound and not state.get("topic_mismatch"):
        out["needs_user_data"] = False
    return out
