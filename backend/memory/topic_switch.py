"""Robust subject / topic-switch detection for dataset binding.

Used by /v1/ask, memory inject, and cache so that:

  Upload India GDP → Analyze IPL

never keeps the GDP file bound.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from backend.memory.continuity import (
    is_follow_up_question,
    is_new_dataset_topic,
    tokenize_content,
)

logger = logging.getLogger(__name__)


def path_topic_tokens(path: str | None) -> set[str]:
    """Derive content tokens from a filesystem path / URL basename."""
    if not path:
        return set()
    name = Path(str(path).replace("\\", "/").split("/")[-1]).stem
    # india_gdp → india gdp
    name = name.replace("_", " ").replace("-", " ")
    return tokenize_content(name)


def bound_topic_blob(
    *,
    dataset_topic: str | None = None,
    dataset_name: str | None = None,
    dataset_path: str | None = None,
    file_path: str | None = None,
) -> str:
    parts = [
        dataset_topic or "",
        dataset_name or "",
        " ".join(path_topic_tokens(dataset_path)),
        " ".join(path_topic_tokens(file_path)),
    ]
    return " ".join(p for p in parts if p).strip()


def detect_topic_switch(
    question: str | None,
    *,
    dataset_topic: str | None = None,
    dataset_name: str | None = None,
    dataset_path: str | None = None,
    file_path: str | None = None,
    has_active_dataset: bool | None = None,
) -> bool:
    """
    True when the user asks about a *different subject* than the bound dataset.

    Works for arbitrary subjects (IPL, Olympics, stocks, …) via content tokens —
    not a fixed keyword list.
    """
    q = (question or "").strip()
    if not q:
        return False

    bound = bound_topic_blob(
        dataset_topic=dataset_topic,
        dataset_name=dataset_name,
        dataset_path=dataset_path,
        file_path=file_path,
    )
    has_binding = (
        has_active_dataset
        if has_active_dataset is not None
        else bool(dataset_path or file_path or dataset_topic or dataset_name)
    )
    if not has_binding:
        return False

    # Explicit "use this upload" language → keep file
    low = q.lower()
    if any(
        p in low
        for p in (
            "this file",
            "my file",
            "uploaded",
            "this csv",
            "this dataset",
            "the uploaded",
        )
    ):
        return False

    return is_new_dataset_topic(
        q,
        bound or dataset_topic or dataset_name,
        has_active_dataset=True,
    )


def release_bound_file_if_topic_switch(
    question: str | None,
    file_path: str | None,
    *,
    session_topic: str | None = None,
    session_name: str | None = None,
    session_path: str | None = None,
) -> tuple[Optional[str], bool]:
    """
    Returns (file_path_or_None, topic_switch).

    If the client still sends the *old* upload path while asking a new subject,
    strip the path so retrieval can run.
    """
    if not file_path:
        switch = detect_topic_switch(
            question,
            dataset_topic=session_topic,
            dataset_name=session_name,
            dataset_path=session_path,
            file_path=None,
            has_active_dataset=bool(session_path or session_topic),
        )
        return None, switch

    # Path present: compare question subject to path + session labels
    switch = detect_topic_switch(
        question,
        dataset_topic=session_topic,
        dataset_name=session_name,
        dataset_path=session_path or file_path,
        file_path=file_path,
        has_active_dataset=True,
    )
    if switch:
        logger.info(
            "Topic switch — releasing bound file_path",
            extra={
                "question": (question or "")[:100],
                "released_path": file_path,
                "session_topic": session_topic,
            },
        )
        return None, True
    return file_path, False


def apply_topic_switch_to_state(
    state: dict[str, Any],
    *,
    force: bool = False,
    active_topic: str | None = None,
    active_path: str | None = None,
) -> dict[str, Any]:
    """
    Mutate graph state when topic switches: clear paths, set flags, log diagnostics.

    force=True: caller already decided mismatch (do not re-detect from incomplete state).
    """
    state = state if isinstance(state, dict) else {}
    question = state.get("question") or state.get("raw_question")
    path = (
        state.get("file_path")
        or state.get("local_path")
        or state.get("dataset_path")
        or active_path
    )
    if not force:
        switch = detect_topic_switch(
            question,
            dataset_topic=state.get("dataset_topic")
            or state.get("session_dataset_topic")
            or active_topic,
            dataset_name=state.get("dataset_name"),
            dataset_path=state.get("dataset_path") or active_path,
            file_path=path,
            has_active_dataset=bool(
                path
                or state.get("dataset_url")
                or state.get("data") is not None
                or state.get("dataset_topic")
                or active_topic
                or active_path
            ),
        )
        if not switch:
            return state

    state["topic_mismatch"] = True
    state["force_reload_dataset"] = True
    state["reuse_active_dataset"] = False
    state["planner_skip_upload"] = False
    state["has_active_dataset"] = False
    # Release bindings
    for key in (
        "file_path",
        "local_path",
        "dataset_path",
        "dataset_url",
        "dataset_fingerprint",
        "data",
        "dataset_id",
    ):
        state.pop(key, None)
    # Drop old topic labels so discovery uses the new question
    state.pop("dataset_topic", None)
    state.pop("dataset_name", None)

    logger.info(
        "Topic switch applied to graph state",
        extra={
            "question": (question or "")[:100],
            "topic_mismatch": True,
            "reuse_dataset": False,
            "file_path": None,
        },
    )
    return state


def log_dataset_binding_decision(
    *,
    prompt: str | None,
    planner_topic: str | None = None,
    current_dataset: str | None = None,
    reuse_dataset: bool,
    topic_mismatch: bool,
    file_path: str | None,
    cache_key: str | None = None,
    provider: str | None = None,
    dataset_loaded: str | None = None,
) -> None:
    """Structured diagnostics for /v1/ask topic switching."""
    logger.info(
        "DATASET_BINDING",
        extra={
            "incoming_prompt": (prompt or "")[:120],
            "planner_topic": planner_topic,
            "current_dataset": current_dataset,
            "reuse_dataset": reuse_dataset,
            "topic_mismatch": topic_mismatch,
            "file_path": file_path,
            "cache_key": (cache_key or "")[:64] or None,
            "selected_provider": provider,
            "dataset_loaded": dataset_loaded,
        },
    )
