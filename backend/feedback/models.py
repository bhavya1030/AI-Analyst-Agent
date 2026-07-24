"""Models for Human Feedback Learning.

Stores user feedback and score adjustments. RLHF-ready without redesign.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class FeedbackType(str, Enum):
    """Supported user feedback labels."""

    WRONG_DATASET = "wrong_dataset"
    WRONG_CHART = "wrong_chart"
    BAD_EXPLANATION = "bad_explanation"
    WRONG_FORECAST = "wrong_forecast"
    POOR_VISUALIZATION = "poor_visualization"
    GOOD_ANSWER = "good_answer"
    EXCELLENT_ANSWER = "excellent_answer"

    @classmethod
    def parse(cls, value: str | "FeedbackType") -> "FeedbackType":
        if isinstance(value, FeedbackType):
            return value
        raw = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "wrong_dataset": cls.WRONG_DATASET,
            "bad_dataset": cls.WRONG_DATASET,
            "wrong_chart": cls.WRONG_CHART,
            "bad_chart": cls.WRONG_CHART,
            "bad_explanation": cls.BAD_EXPLANATION,
            "wrong_explanation": cls.BAD_EXPLANATION,
            "wrong_forecast": cls.WRONG_FORECAST,
            "bad_forecast": cls.WRONG_FORECAST,
            "poor_visualization": cls.POOR_VISUALIZATION,
            "bad_visualization": cls.POOR_VISUALIZATION,
            "poor_viz": cls.POOR_VISUALIZATION,
            "good_answer": cls.GOOD_ANSWER,
            "good": cls.GOOD_ANSWER,
            "excellent_answer": cls.EXCELLENT_ANSWER,
            "excellent": cls.EXCELLENT_ANSWER,
            "great": cls.EXCELLENT_ANSWER,
        }
        if raw in aliases:
            return aliases[raw]
        try:
            return cls(raw)
        except ValueError as exc:
            raise ValueError(f"Unknown feedback type: {value}") from exc


# Scalar reward in [-1, 1] — RLHF-ready preference signal
FEEDBACK_REWARDS: dict[FeedbackType, float] = {
    FeedbackType.WRONG_DATASET: -0.8,
    FeedbackType.WRONG_CHART: -0.5,
    FeedbackType.BAD_EXPLANATION: -0.5,
    FeedbackType.WRONG_FORECAST: -0.7,
    FeedbackType.POOR_VISUALIZATION: -0.5,
    FeedbackType.GOOD_ANSWER: 0.6,
    FeedbackType.EXCELLENT_ANSWER: 1.0,
}


@dataclass
class FeedbackRecord:
    """
    One user feedback event.

    Required store fields:
      question, chosen dataset, selected tools, planner output,
      feedback, timestamp, user
    """

    feedback_id: str
    question: str
    feedback: FeedbackType
    user: str = "anonymous"
    timestamp: str = field(default_factory=_utc_now_iso)
    chosen_dataset: Optional[dict[str, Any]] = None
    selected_tools: list[Any] = field(default_factory=list)
    planner_output: Optional[dict[str, Any]] = None
    # Optional context for ranking keys
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    comment: str = ""
    # RLHF-ready fields (unused by rule scorer today)
    reward: float = 0.0
    trajectory_id: Optional[str] = None  # groups multi-step episodes
    preference_rank: Optional[int] = None  # lower = preferred in pairwise prefs
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "question": self.question,
            "feedback": self.feedback.value
            if isinstance(self.feedback, FeedbackType)
            else self.feedback,
            "user": self.user,
            "timestamp": self.timestamp,
            "chosen_dataset": self.chosen_dataset,
            "selected_tools": list(self.selected_tools),
            "planner_output": self.planner_output,
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "comment": self.comment,
            "reward": self.reward,
            "trajectory_id": self.trajectory_id,
            "preference_rank": self.preference_rank,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FeedbackRecord":
        data = data or {}
        fb = data.get("feedback") or FeedbackType.GOOD_ANSWER
        if not isinstance(fb, FeedbackType):
            fb = FeedbackType.parse(str(fb))
        reward = data.get("reward")
        if reward is None:
            reward = FEEDBACK_REWARDS.get(fb, 0.0)
        return cls(
            feedback_id=str(data.get("feedback_id") or data.get("id") or uuid.uuid4().hex),
            question=str(data.get("question") or ""),
            feedback=fb,
            user=str(data.get("user") or "anonymous"),
            timestamp=str(data.get("timestamp") or _utc_now_iso()),
            chosen_dataset=data.get("chosen_dataset")
            if isinstance(data.get("chosen_dataset"), dict)
            else (
                {"topic": data["chosen_dataset"]}
                if isinstance(data.get("chosen_dataset"), str)
                else None
            ),
            selected_tools=list(data.get("selected_tools") or []),
            planner_output=data.get("planner_output")
            if isinstance(data.get("planner_output"), dict)
            else None,
            conversation_id=data.get("conversation_id"),
            session_id=data.get("session_id"),
            comment=str(data.get("comment") or ""),
            reward=float(reward),
            trajectory_id=data.get("trajectory_id"),
            preference_rank=data.get("preference_rank"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ScoreAdjustment:
    """
    Delta scores produced from feedback history.

    Callers apply these to dataset ranking, tool selection,
    planner confidence, and semantic ranking without changing those modules.
    """

    dataset_scores: dict[str, float] = field(default_factory=dict)  # key → delta
    tool_scores: dict[str, float] = field(default_factory=dict)
    planner_confidence_delta: float = 0.0
    semantic_scores: dict[str, float] = field(default_factory=dict)  # query/topic key → delta
    # RLHF-ready aggregates
    mean_reward: float = 0.0
    n_feedback: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ScoreAdjustment":
        data = data or {}
        return cls(
            dataset_scores={str(k): float(v) for k, v in (data.get("dataset_scores") or {}).items()},
            tool_scores={str(k): float(v) for k, v in (data.get("tool_scores") or {}).items()},
            planner_confidence_delta=float(data.get("planner_confidence_delta") or 0.0),
            semantic_scores={
                str(k): float(v) for k, v in (data.get("semantic_scores") or {}).items()
            },
            mean_reward=float(data.get("mean_reward") or 0.0),
            n_feedback=int(data.get("n_feedback") or 0),
            by_type={str(k): int(v) for k, v in (data.get("by_type") or {}).items()},
            reason=str(data.get("reason") or ""),
            metadata=dict(data.get("metadata") or {}),
        )

    def apply_to_score(self, base: float, *, kind: str, key: str) -> float:
        """Apply adjustment for a ranking kind/key; clamps to [0, 1] by default for ranks."""
        delta = 0.0
        if kind == "dataset":
            delta = self.dataset_scores.get(key, 0.0)
        elif kind == "tool":
            delta = self.tool_scores.get(key, 0.0)
        elif kind == "semantic":
            delta = self.semantic_scores.get(key, 0.0)
        elif kind == "planner":
            delta = self.planner_confidence_delta
        return max(0.0, min(1.0, float(base) + delta))


@dataclass
class FeedbackQuery:
    """Filter for get_feedback()."""

    user: Optional[str] = None
    feedback_type: Optional[FeedbackType] = None
    question_contains: Optional[str] = None
    dataset_key: Optional[str] = None
    conversation_id: Optional[str] = None
    since: Optional[str] = None
    limit: int = 100
