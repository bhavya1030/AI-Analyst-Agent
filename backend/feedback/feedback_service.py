"""Human Feedback Learning service.

Exposes:
  record_feedback()
  get_feedback()
  adjust_scores()

Does not modify Planner / Retrieval / Tool Selection — only produces adjustments.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional, Sequence

from backend.core.logger import get_logger
from backend.feedback.memory import FeedbackMemory, get_default_memory
from backend.feedback.models import (
    FEEDBACK_REWARDS,
    FeedbackQuery,
    FeedbackRecord,
    FeedbackType,
    ScoreAdjustment,
    _utc_now_iso,
)
from backend.feedback.scorer import FeedbackScorer

logger = get_logger(__name__)


class FeedbackService:
    """Record user feedback and derive ranking score adjustments."""

    def __init__(
        self,
        memory: FeedbackMemory | None = None,
        scorer: FeedbackScorer | None = None,
    ):
        self._memory = memory or get_default_memory()
        self._scorer = scorer or FeedbackScorer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_feedback(
        self,
        *,
        question: str,
        feedback: str | FeedbackType,
        user: str = "anonymous",
        chosen_dataset: Any = None,
        selected_tools: Sequence[Any] | None = None,
        planner_output: Any = None,
        conversation_id: str | None = None,
        session_id: str | None = None,
        comment: str = "",
        trajectory_id: str | None = None,
        preference_rank: int | None = None,
        metadata: dict[str, Any] | None = None,
        feedback_id: str | None = None,
        timestamp: str | None = None,
    ) -> FeedbackRecord:
        """
        Persist a feedback event.

        Stores: question, chosen dataset, selected tools, planner output,
        feedback, timestamp, user (+ RLHF fields).
        """
        fb = FeedbackType.parse(feedback)
        ds = _normalize_dataset(chosen_dataset)
        tools = list(selected_tools or [])
        plan = _normalize_planner(planner_output)
        reward = FEEDBACK_REWARDS.get(fb, 0.0)

        record = FeedbackRecord(
            feedback_id=feedback_id or uuid.uuid4().hex,
            question=(question or "").strip(),
            feedback=fb,
            user=(user or "anonymous").strip() or "anonymous",
            timestamp=timestamp or _utc_now_iso(),
            chosen_dataset=ds,
            selected_tools=tools,
            planner_output=plan,
            conversation_id=conversation_id,
            session_id=session_id,
            comment=comment or "",
            reward=reward,
            trajectory_id=trajectory_id,
            preference_rank=preference_rank,
            metadata=dict(metadata or {}),
        )
        if not record.question:
            raise ValueError("question is required")

        stored = self._memory.add(record)
        logger.info(
            "Feedback recorded",
            extra={
                "feedback_id": stored.feedback_id,
                "type": stored.feedback.value,
                "user": stored.user,
                "reward": stored.reward,
            },
        )
        return stored

    def get_feedback(
        self,
        *,
        feedback_id: str | None = None,
        user: str | None = None,
        feedback_type: str | FeedbackType | None = None,
        question_contains: str | None = None,
        dataset_key: str | None = None,
        conversation_id: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> FeedbackRecord | list[FeedbackRecord] | None:
        """
        Fetch one record by id, or a filtered list.
        """
        if feedback_id:
            return self._memory.get(feedback_id)

        ft = None
        if feedback_type is not None:
            ft = (
                feedback_type
                if isinstance(feedback_type, FeedbackType)
                else FeedbackType.parse(str(feedback_type))
            )
        query = FeedbackQuery(
            user=user,
            feedback_type=ft,
            question_contains=question_contains,
            dataset_key=dataset_key,
            conversation_id=conversation_id,
            since=since,
            limit=limit,
        )
        return self._memory.list(query)

    def adjust_scores(
        self,
        *,
        question: str | None = None,
        dataset_key: str | None = None,
        tool_ids: Sequence[str] | None = None,
        user: str | None = None,
        limit: int = 500,
    ) -> ScoreAdjustment:
        """
        Compute score adjustments from stored feedback.

        Use returned deltas to adjust:
          - Dataset ranking
          - Tool selection
          - Planner confidence
          - Semantic ranking
        """
        # Pull relevant history (optionally user-scoped)
        records = self._memory.list(
            FeedbackQuery(user=user, question_contains=None, limit=limit)
        )
        # If question filter desired for listing, scorer also filters loosely
        if question:
            # Prefer records related to question, but include global if few
            related = [
                r
                for r in records
                if _tokens_overlap(question, r.question) or not r.question
            ]
            if len(related) >= 1:
                # mix: related first then rest for global prior
                seen = {r.feedback_id for r in related}
                mixed = related + [r for r in records if r.feedback_id not in seen]
                records = mixed[:limit]

        adj = self._scorer.score(
            records,
            question=question,
            dataset_key=dataset_key,
            tool_ids=list(tool_ids) if tool_ids else None,
        )
        logger.info(
            "Score adjustments computed",
            extra={
                "n_feedback": adj.n_feedback,
                "planner_delta": adj.planner_confidence_delta,
                "n_datasets": len(adj.dataset_scores),
                "n_tools": len(adj.tool_scores),
            },
        )
        return adj

    # ------------------------------------------------------------------
    # RLHF helpers (future-ready, no training here)
    # ------------------------------------------------------------------

    def record_preference_pair(
        self,
        *,
        question: str,
        chosen: dict[str, Any],
        rejected: dict[str, Any],
        user: str = "anonymous",
        **kwargs: Any,
    ) -> tuple[FeedbackRecord, FeedbackRecord]:
        """
        Store a pairwise preference (chosen > rejected) for future RLHF.

        Each side is a trajectory snippet with dataset/tools/planner fields.
        """
        traj = kwargs.get("trajectory_id") or uuid.uuid4().hex
        chosen_rec = self.record_feedback(
            question=question,
            feedback=FeedbackType.EXCELLENT_ANSWER,
            user=user,
            chosen_dataset=chosen.get("chosen_dataset") or chosen.get("dataset"),
            selected_tools=chosen.get("selected_tools") or chosen.get("tools"),
            planner_output=chosen.get("planner_output") or chosen.get("plan"),
            trajectory_id=traj,
            preference_rank=0,
            metadata={"pair_role": "chosen", **dict(chosen.get("metadata") or {})},
            comment=kwargs.get("comment") or "preference_pair_chosen",
        )
        rejected_rec = self.record_feedback(
            question=question,
            feedback=FeedbackType.WRONG_DATASET
            if rejected.get("kind") == "dataset"
            else FeedbackType.BAD_EXPLANATION,
            user=user,
            chosen_dataset=rejected.get("chosen_dataset") or rejected.get("dataset"),
            selected_tools=rejected.get("selected_tools") or rejected.get("tools"),
            planner_output=rejected.get("planner_output") or rejected.get("plan"),
            trajectory_id=traj,
            preference_rank=1,
            metadata={"pair_role": "rejected", **dict(rejected.get("metadata") or {})},
            comment=kwargs.get("comment") or "preference_pair_rejected",
        )
        return chosen_rec, rejected_rec

    def export_rlhf_dataset(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Export records as RLHF-friendly dicts (prompt, completion keys, reward)."""
        rows = []
        for r in self._memory.list(FeedbackQuery(limit=limit)):
            rows.append(
                {
                    "prompt": r.question,
                    "feedback_type": r.feedback.value
                    if isinstance(r.feedback, FeedbackType)
                    else r.feedback,
                    "reward": r.reward,
                    "dataset": r.chosen_dataset,
                    "tools": r.selected_tools,
                    "planner": r.planner_output,
                    "user": r.user,
                    "timestamp": r.timestamp,
                    "trajectory_id": r.trajectory_id,
                    "preference_rank": r.preference_rank,
                }
            )
        return rows


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_default_service: FeedbackService | None = None


def get_feedback_service() -> FeedbackService:
    global _default_service
    if _default_service is None:
        _default_service = FeedbackService()
    return _default_service


def reset_feedback_service() -> None:
    global _default_service
    from backend.feedback.memory import reset_default_memory

    _default_service = None
    reset_default_memory()


def record_feedback(**kwargs: Any) -> FeedbackRecord:
    return get_feedback_service().record_feedback(**kwargs)


def get_feedback(**kwargs: Any) -> FeedbackRecord | list[FeedbackRecord] | None:
    return get_feedback_service().get_feedback(**kwargs)


def adjust_scores(**kwargs: Any) -> ScoreAdjustment:
    return get_feedback_service().adjust_scores(**kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_dataset(value: Any) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"topic": value}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {"value": str(value)}


def _normalize_planner(value: Any) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {"value": str(value)}


def _tokens_overlap(a: str, b: str) -> bool:
    stop = {
        "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "show",
        "analyze", "analyse", "please",
    }
    ta = {t for t in re_tokens(a) if t not in stop and len(t) > 2}
    tb = {t for t in re_tokens(b) if t not in stop and len(t) > 2}
    if not ta or not tb:
        return False
    return bool(ta & tb)


def re_tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9]+", (text or "").lower())
