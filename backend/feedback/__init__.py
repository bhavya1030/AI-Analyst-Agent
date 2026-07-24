"""Human Feedback Learning — improve future decisions from user feedback.

Does not modify Planner, Retrieval, Tool Selection, or Semantic Search.
Produces score adjustments those systems can apply later.
"""

from backend.feedback.feedback_service import (
    FeedbackService,
    adjust_scores,
    get_feedback,
    get_feedback_service,
    record_feedback,
    reset_feedback_service,
)
from backend.feedback.memory import FeedbackMemory, get_default_memory, reset_default_memory
from backend.feedback.models import (
    FEEDBACK_REWARDS,
    FeedbackQuery,
    FeedbackRecord,
    FeedbackType,
    ScoreAdjustment,
)
from backend.feedback.scorer import FeedbackScorer

__all__ = [
    # API
    "record_feedback",
    "get_feedback",
    "adjust_scores",
    "FeedbackService",
    "get_feedback_service",
    "reset_feedback_service",
    # Models
    "FeedbackType",
    "FeedbackRecord",
    "ScoreAdjustment",
    "FeedbackQuery",
    "FEEDBACK_REWARDS",
    # Internals
    "FeedbackMemory",
    "FeedbackScorer",
    "get_default_memory",
    "reset_default_memory",
]
