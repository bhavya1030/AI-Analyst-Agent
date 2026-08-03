"""Conversation Memory v2 — continuity helpers.

Detect follow-up analysis operations vs true topic changes so the planner
reuses the session dataset instead of asking for upload again.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Tokens that describe *what to do* with data, not *which dataset*.
# Tokens that describe *what to do* with data, not *which dataset*.
OPERATION_TOKENS = frozenset(
    {
        # Data Quality, Structure & Inspection
        "show", "plot", "chart", "graph", "visualize", "visualise", "draw", "display", "render",
        "missing", "null", "nulls", "nan", "nans", "na", "duplicate", "duplicates", "shape", "head", "tail",
        "column", "columns", "dtype", "dtypes", "types", "info", "unique", "uniques", "structure", "schema",
        "raw", "clean", "cleaned", "cleaning",
        # Summary & Descriptive Statistics
        "describe", "summary", "stats", "statistics", "overview", "mean", "median", "mode",
        "average", "avg", "min", "minimum", "max", "maximum", "std", "variance", "var",
        "count", "sum", "total", "quantile", "percentile", "skew", "kurtosis",
        # EDA & Analytical Patterns
        "eda", "exploration", "analysis", "analyze", "analyse", "inspect", "examine",
        "investigate", "study", "insight", "insights", "pattern", "patterns", "outlier",
        "outliers", "cluster", "clusters", "clustering", "correlation", "correlate",
        "corr", "covariation", "covariance", "importance", "relation", "relationship",
        # Visualization Types
        "histogram", "hist", "bar", "line", "scatter", "box", "boxplot", "pie", "heatmap",
        "distribution", "density", "matrix", "figure", "fig",
        # Forecasting & Trends
        "forecast", "predict", "projection", "trend", "trends",
        # Comparison, Filtering & Operations
        "compare", "comparison", "versus", "vs", "filter", "group", "groupby", "by", "top",
        "bottom", "rank", "slice", "sort", "order",
        # Language Stopwords & Data References
        "again", "another", "same", "more", "please", "help", "next", "previous", "past",
        "last", "years", "year", "months", "the", "a", "an", "and", "or", "of", "for",
        "to", "in", "on", "with", "from", "it", "this", "that", "them", "those", "data",
        "dataset", "file", "csv", "excel", "table", "frame", "dataframe", "row", "rows",
        "variable", "variables", "value", "values", "using", "use", "make", "create",
        "generate", "give", "rate", "rates", "price", "prices", "over", "time", "series",
    }
)

FOLLOW_UP_PHRASES = (
    "show missing values",
    "missing values",
    "null values",
    "show duplicates",
    "duplicates",
    "describe dataset",
    "describe data",
    "describe",
    "summary statistics",
    "summary",
    "correlation matrix",
    "correlation",
    "heatmap",
    "plot histogram",
    "histogram",
    "bar chart",
    "scatter plot",
    "pie chart",
    "box plot",
    "distribution",
    "average",
    "mean",
    "median",
    "count",
    "data types",
    "columns",
    "unique values",
    "outliers",
    "clusters",
    "feature importance",
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
    """True for analytical operations, data inspection, or pronoun follow-ups that keep active dataset."""
    q = (question or "").strip().lower()
    if not q:
        return False

    # Open-world analyze verbs with distinct subjects (e.g. "analyze gold prices") are not follow-ups
    open_world_verbs = (
        "analyze ", "analyse ", "study ", "explore ", "dataset about", "data on ", "data about ",
        "load dataset", "switch to", "open dataset", "fetch dataset", "use dataset", "search dataset",
        "find dataset", "download dataset", "search for data", "get dataset", "import dataset"
    )

    if any(p in q for p in FOLLOW_UP_PHRASES):
        if not any(v in q for v in open_world_verbs):
            return True

    if PRONOUN_RE.search(q) and len(q.split()) <= 14:
        return True

    content = tokenize_content(q)
    if not content and len(q.split()) <= 10:
        if not any(v in q for v in open_world_verbs):
            return True

    # High ratio of operation / analytical tokens when no new subject is present
    words = [w for w in re.findall(r"[a-z0-9]+", q) if len(w) > 1]
    if words and not content:
        op_count = sum(
            1
            for w in words
            if w in OPERATION_TOKENS or w in {"show", "values", "value", "data", "dataset"}
        )
        if (op_count / len(words)) >= 0.5:
            if not any(v in q for v in open_world_verbs):
                return True

    return False


def is_new_dataset_topic(
    question: str | None,
    active_topic: str | None,
    *,
    has_active_dataset: bool = False,
) -> bool:
    """
    True when the user requests a *different dataset subject* than the bound session dataset.

    Follow-up analytical operations (e.g. "show missing values", "describe dataset",
    "summary statistics", "correlation matrix", "plot histogram", "average age")
    return False so the active dataset is preserved.
    """
    if not question or not question.strip():
        return False

    lowered = question.lower().strip()

    explicit_switch_verbs = (
        "switch to", "load dataset", "open dataset", "fetch dataset", "use dataset",
        "search dataset", "find dataset", "download dataset", "dataset about", "data on ",
        "data about ", "import dataset", "load file", "open file"
    )
    is_explicit_switch = any(v in lowered for v in explicit_switch_verbs)
    open_analyze = any(v in lowered for v in ("analyze ", "analyse ", "study ", "explore "))

    if has_active_dataset:
        if is_follow_up_question(question) and not is_explicit_switch:
            if open_analyze:
                q_content = tokenize_content(question)
                t_content = tokenize_content(active_topic)
                if q_content and t_content and not (q_content & t_content):
                    return True
            return False

    q_tokens = tokenize_content(question)
    t_tokens = tokenize_content(active_topic)

    if not q_tokens:
        return False

    if not t_tokens:
        if has_active_dataset:
            if is_follow_up_question(question):
                return False
            if not is_explicit_switch and not open_analyze:
                return False
        return bool(q_tokens)

    if q_tokens & t_tokens:
        return False

    if has_active_dataset and is_follow_up_question(question) and not is_explicit_switch:
        return False

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

    Critical: a client may still send the *old* upload path while asking about a
    new subject (Upload GDP → "Analyze IPL"). That must set topic_mismatch=True
    so callers strip file_path and run retrieval.
    """
    from pathlib import Path

    def _path_tokens(p: str | None) -> set[str]:
        if not p:
            return set()
        stem = Path(str(p).replace("\\", "/").split("/")[-1]).stem
        return tokenize_content(stem.replace("_", " ").replace("-", " "))

    # Active label = session topic + path stems (session + override)
    active_label = " ".join(
        filter(
            None,
            [
                dataset_topic or "",
                " ".join(_path_tokens(dataset_path)),
                " ".join(_path_tokens(file_path_override)),
            ],
        )
    )

    if file_path_override:
        # Does the question match this file? (new upload for the new topic)
        q_tok = tokenize_content(question)
        p_tok = _path_tokens(file_path_override)
        if q_tok and p_tok and (q_tok & p_tok):
            # e.g. uploaded ipl.csv + "Analyze IPL" → keep file
            return False, False
        # Does the question match the *session* topic/path (same dataset)?
        s_tok = tokenize_content(dataset_topic) | _path_tokens(dataset_path)
        if q_tok and s_tok and (q_tok & s_tok):
            return False, False
        # Question is a pure follow-up → keep bound file
        if is_follow_up_question(question) and not is_new_dataset_topic(
            question, active_label or dataset_topic, has_active_dataset=True
        ):
            return False, False
        # Distinct subject vs bound file (GDP file + "Analyze IPL")
        if is_new_dataset_topic(
            question, active_label or dataset_topic or " ".join(p_tok), has_active_dataset=True
        ):
            return False, True
        return False, False

    has_binding = bool(dataset_path or dataset_url or has_frame)
    if not has_binding:
        return False, False

    mismatch = is_new_dataset_topic(
        question,
        active_label or dataset_topic,
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
