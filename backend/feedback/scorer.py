"""Convert feedback history into ranking score adjustments.

Produces deltas for:
  - Dataset ranking
  - Tool selection
  - Planner confidence
  - Semantic ranking

Does not mutate those modules — callers apply deltas.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Optional

from backend.feedback.models import (
    FEEDBACK_REWARDS,
    FeedbackRecord,
    FeedbackType,
    ScoreAdjustment,
)


def _norm_key(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip().lower())
    return s


def dataset_key_from_record(record: FeedbackRecord) -> str:
    ds = record.chosen_dataset or {}
    if isinstance(ds, dict):
        return _norm_key(
            str(
                ds.get("dataset_id")
                or ds.get("topic")
                or ds.get("title")
                or ds.get("local_path")
                or ""
            )
        )
    return _norm_key(str(ds))


def tool_ids_from_record(record: FeedbackRecord) -> list[str]:
    out: list[str] = []
    for t in record.selected_tools or []:
        if isinstance(t, dict):
            tid = t.get("tool_id") or t.get("name") or t.get("id")
            if tid:
                out.append(_norm_key(str(tid)))
        elif t:
            out.append(_norm_key(str(t)))
    return out


def semantic_key_from_record(record: FeedbackRecord) -> str:
    """Topic / question stem used for semantic ranking boosts."""
    ds = record.chosen_dataset or {}
    topic = ""
    if isinstance(ds, dict):
        topic = str(ds.get("topic") or ds.get("title") or "")
    if not topic and record.planner_output:
        topics = record.planner_output.get("topics") or []
        if topics:
            topic = str(topics[0])
    if not topic:
        # first few content tokens from question
        tokens = re.findall(r"[a-z0-9]+", (record.question or "").lower())
        stop = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "show", "analyze"}
        topic = " ".join(t for t in tokens if t not in stop)[:80]
    return _norm_key(topic)


class FeedbackScorer:
    """
    Aggregate feedback into ScoreAdjustment.

    Negative feedback on a component decreases its score; positive increases it.
    Magnitudes are small so a few votes do not dominate base rankers.
    """

    # Per-event deltas (clamped later when applied)
    DATASET_DELTA = {
        FeedbackType.WRONG_DATASET: -0.15,
        FeedbackType.GOOD_ANSWER: 0.05,
        FeedbackType.EXCELLENT_ANSWER: 0.10,
    }
    TOOL_DELTA = {
        FeedbackType.WRONG_CHART: -0.12,
        FeedbackType.POOR_VISUALIZATION: -0.12,
        FeedbackType.WRONG_FORECAST: -0.15,
        FeedbackType.GOOD_ANSWER: 0.04,
        FeedbackType.EXCELLENT_ANSWER: 0.08,
    }
    # Tools most associated with chart/viz/forecast feedback
    CHART_TOOLS = frozenset(
        {"visualization", "scatter_plot", "histogram", "trend", "viz"}
    )
    FORECAST_TOOLS = frozenset({"forecast", "time_series", "trend"})
    EXPLAIN_HINT = "explain"

    PLANNER_DELTA = {
        FeedbackType.WRONG_DATASET: -0.05,
        FeedbackType.WRONG_FORECAST: -0.04,
        FeedbackType.BAD_EXPLANATION: -0.03,
        FeedbackType.GOOD_ANSWER: 0.03,
        FeedbackType.EXCELLENT_ANSWER: 0.06,
        FeedbackType.WRONG_CHART: -0.02,
        FeedbackType.POOR_VISUALIZATION: -0.02,
    }

    SEMANTIC_DELTA = {
        FeedbackType.WRONG_DATASET: -0.10,
        FeedbackType.GOOD_ANSWER: 0.04,
        FeedbackType.EXCELLENT_ANSWER: 0.08,
    }

    def score(
        self,
        records: Iterable[FeedbackRecord],
        *,
        question: str | None = None,
        dataset_key: str | None = None,
        tool_ids: list[str] | None = None,
    ) -> ScoreAdjustment:
        """
        Build aggregate adjustments.

        Optional filters focus deltas on a query/dataset/tool context
        (still uses full history for global component stats).
        """
        records = list(records)
        dataset_scores: dict[str, float] = defaultdict(float)
        tool_scores: dict[str, float] = defaultdict(float)
        semantic_scores: dict[str, float] = defaultdict(float)
        planner_delta = 0.0
        rewards: list[float] = []
        by_type: dict[str, int] = defaultdict(int)

        q_filter = _norm_key(question) if question else None
        ds_filter = _norm_key(dataset_key) if dataset_key else None
        tool_filter = {_norm_key(t) for t in (tool_ids or []) if t}

        for rec in records:
            fb = rec.feedback if isinstance(rec.feedback, FeedbackType) else FeedbackType.parse(
                str(rec.feedback)
            )
            by_type[fb.value] += 1
            reward = rec.reward if rec.reward is not None else FEEDBACK_REWARDS.get(fb, 0.0)
            rewards.append(float(reward))

            # Optional contextual filtering: still count global type stats,
            # but only apply ranking deltas when context matches (or no filter).
            if q_filter and q_filter not in _norm_key(rec.question):
                # loose: also allow empty question records
                if rec.question:
                    # still apply global planner tiny signal? skip ranking keys
                    planner_delta += self.PLANNER_DELTA.get(fb, 0.0) * 0.25
                    continue

            dkey = dataset_key_from_record(rec)
            if dkey and (not ds_filter or ds_filter == dkey or ds_filter in dkey):
                if fb in self.DATASET_DELTA:
                    dataset_scores[dkey] += self.DATASET_DELTA[fb]
                elif fb == FeedbackType.WRONG_DATASET:
                    dataset_scores[dkey] += -0.15

            # Tools
            tids = tool_ids_from_record(rec)
            if not tids and rec.planner_output:
                # fallback from planner tool list
                for t in rec.planner_output.get("tool_ids") or rec.planner_output.get(
                    "selected_tools"
                ) or []:
                    if isinstance(t, dict):
                        tids.append(_norm_key(str(t.get("tool_id") or t.get("name") or "")))
                    else:
                        tids.append(_norm_key(str(t)))
            tids = [t for t in tids if t]

            for tid in tids:
                if tool_filter and tid not in tool_filter:
                    continue
                if fb in self.TOOL_DELTA:
                    # Scope chart/forecast penalties to relevant tools when possible
                    if fb in {
                        FeedbackType.WRONG_CHART,
                        FeedbackType.POOR_VISUALIZATION,
                    }:
                        if tid in self.CHART_TOOLS or not (self.CHART_TOOLS & set(tids)):
                            tool_scores[tid] += self.TOOL_DELTA[fb]
                    elif fb == FeedbackType.WRONG_FORECAST:
                        if tid in self.FORECAST_TOOLS or not (self.FORECAST_TOOLS & set(tids)):
                            tool_scores[tid] += self.TOOL_DELTA[fb]
                    else:
                        tool_scores[tid] += self.TOOL_DELTA[fb]
                if fb == FeedbackType.BAD_EXPLANATION and (
                    "explain" in tid or tid in {"insight", "explanation"}
                ):
                    tool_scores[tid] += -0.10

            # If chart feedback but no tools recorded, attribute to visualization
            if fb in {FeedbackType.WRONG_CHART, FeedbackType.POOR_VISUALIZATION} and not tids:
                tool_scores["visualization"] += self.TOOL_DELTA.get(fb, -0.1)
            if fb == FeedbackType.WRONG_FORECAST and not tids:
                tool_scores["forecast"] += self.TOOL_DELTA.get(fb, -0.1)

            # Planner confidence
            planner_delta += self.PLANNER_DELTA.get(fb, 0.0)

            # Semantic ranking on topic/question key
            skey = semantic_key_from_record(rec)
            if skey and fb in self.SEMANTIC_DELTA:
                semantic_scores[skey] += self.SEMANTIC_DELTA[fb]
            # Also index by question tokens for retrieval boosts
            qkey = _norm_key(rec.question)[:100]
            if qkey and fb in self.SEMANTIC_DELTA:
                semantic_scores[qkey] += self.SEMANTIC_DELTA[fb] * 0.5

        # Clamp extreme aggregates (many votes)
        def _clamp_map(m: dict[str, float], lo: float = -0.5, hi: float = 0.5) -> dict[str, float]:
            return {k: max(lo, min(hi, v)) for k, v in m.items() if k}

        mean_reward = sum(rewards) / len(rewards) if rewards else 0.0
        planner_delta = max(-0.3, min(0.2, planner_delta))

        return ScoreAdjustment(
            dataset_scores=_clamp_map(dict(dataset_scores)),
            tool_scores=_clamp_map(dict(tool_scores)),
            planner_confidence_delta=round(planner_delta, 4),
            semantic_scores=_clamp_map(dict(semantic_scores)),
            mean_reward=round(mean_reward, 4),
            n_feedback=len(records),
            by_type=dict(by_type),
            reason=f"Aggregated {len(records)} feedback event(s).",
            metadata={
                "rlhf_ready": True,
                "reward_range": [-1.0, 1.0],
            },
        )
