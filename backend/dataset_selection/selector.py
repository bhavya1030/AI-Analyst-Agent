"""Dataset selectors: abstract interface, rule-based default, LLM placeholder."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.dataset_selection.models import (
    DatasetCandidate,
    SelectionInput,
    SelectionResult,
)
from backend.dataset_selection.prompts import build_selection_prompt

logger = get_logger(__name__)

_STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "for",
    "to",
    "in",
    "on",
    "with",
    "by",
    "from",
    "analyze",
    "analyse",
    "study",
    "explore",
    "show",
    "plot",
    "forecast",
    "predict",
    "dataset",
    "data",
    "please",
}


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 2 and t not in _STOP
    }


class DatasetSelector(ABC):
    """Choose the best dataset among candidates for a user question."""

    name: str = "base"

    @abstractmethod
    def select(self, selection_input: SelectionInput) -> SelectionResult:
        ...

    def select_best_dataset(
        self,
        question: str,
        candidates: list[Any],
        *,
        topic: str = "",
    ) -> SelectionResult:
        """Convenience API used by Retrieval later."""
        return self.select(
            SelectionInput.from_raw(question, candidates, topic=topic)
        )


class RuleBasedSelector(DatasetSelector):
    """
    Default deterministic selector.

    Scores candidates by:
      - token overlap with question/topic
      - semantic similarity_score (if present)
      - rank_hint (if present)
      - loadability (local_path / loadable URL extension)
      - source quality bias (registry/github/world bank slightly preferred)
    """

    name = "rule_based"

    def select(self, selection_input: SelectionInput) -> SelectionResult:
        question = selection_input.question or selection_input.topic or ""
        candidates = list(selection_input.candidates or [])
        if not candidates:
            return SelectionResult(
                best_dataset=None,
                reason="No candidates provided.",
                confidence=0.0,
                selector=self.name,
            )

        if len(candidates) == 1:
            only = candidates[0]
            return SelectionResult(
                best_dataset=only,
                reason="Only one candidate available.",
                confidence=0.9,
                selector=self.name,
                scores={only.candidate_id: 0.9},
                alternatives=[],
            )

        q_tokens = _tokens(question) | _tokens(selection_input.topic)
        scores: dict[str, float] = {}
        scored: list[tuple[float, DatasetCandidate, str]] = []

        for cand in candidates:
            score, reason_bits = self._score_candidate(cand, q_tokens, question)
            scores[cand.candidate_id] = score
            scored.append((score, cand, "; ".join(reason_bits) if reason_bits else "baseline"))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best, best_bits = scored[0]
        # Confidence: normalize by max plausible score (~20) and gap to runner-up
        conf = min(1.0, max(0.05, best_score / 20.0))
        if len(scored) > 1:
            gap = best_score - scored[1][0]
            conf = min(1.0, conf + min(0.2, gap / 20.0))

        alternatives = [c for _, c, _ in scored[1:4]]
        reason = (
            f"Selected '{best.title or best.candidate_id}' "
            f"(score={best_score:.2f}). {best_bits}"
        )
        logger.info(
            "RuleBasedSelector chose dataset",
            extra={
                "best": best.candidate_id,
                "score": best_score,
                "confidence": conf,
                "n": len(candidates),
            },
        )
        return SelectionResult(
            best_dataset=best,
            reason=reason,
            confidence=round(conf, 3),
            selector=self.name,
            scores=scores,
            alternatives=alternatives,
        )

    def _score_candidate(
        self,
        cand: DatasetCandidate,
        q_tokens: set[str],
        question: str,
    ) -> tuple[float, list[str]]:
        score = 0.0
        bits: list[str] = []
        blob = " ".join(
            [
                cand.title,
                cand.topic,
                cand.description,
                cand.summary,
                " ".join(cand.tags),
                " ".join(cand.columns[:20]),
                cand.source,
            ]
        ).lower()
        c_tokens = _tokens(blob)

        overlap = len(q_tokens & c_tokens) if q_tokens else 0
        if q_tokens:
            score += overlap * 3.0
            if overlap:
                bits.append(f"token_overlap={overlap}")
            # phrase containment
            q_low = question.lower()
            if cand.topic and cand.topic.lower() in q_low:
                score += 4.0
                bits.append("topic_in_question")
            if cand.title and any(t in cand.title.lower() for t in q_tokens):
                score += 2.0

        if cand.similarity_score is not None:
            # semantic score typically 0–1
            sem = max(0.0, min(1.0, float(cand.similarity_score)))
            score += sem * 10.0
            bits.append(f"semantic={sem:.2f}")

        if cand.rank_hint is not None:
            score += min(8.0, float(cand.rank_hint) / 2.0)
            bits.append(f"rank_hint={cand.rank_hint}")

        # Loadability preference
        if cand.local_path:
            score += 5.0
            bits.append("has_local_path")
        url = (cand.download_url or "").lower()
        if any(url.endswith(ext) or ext in url for ext in (".csv", ".json", ".parquet", ".xlsx", ".xls")):
            score += 4.0
            bits.append("loadable_url")
        elif url.startswith("http"):
            score += 1.0

        source = (cand.source or cand.source_type or "").lower()
        if any(s in source for s in ("world bank", "github", "registry", "trusted")):
            score += 1.5
            bits.append("trusted_source")
        if "wikipedia" in source:
            score -= 1.0  # usually not a ready tabular file

        provider = (cand.provider or "").lower()
        if "registry" in provider or "semantic" in provider:
            score += 1.0

        return score, bits


class LLMDatasetSelector(DatasetSelector):
    """
    Placeholder LLM selector.

    Currently delegates to RuleBasedSelector so the interface is live.
    Later: call Ollama with build_selection_prompt() and parse JSON.
    """

    name = "llm"

    def __init__(self, fallback: DatasetSelector | None = None):
        self._fallback = fallback or RuleBasedSelector()

    def select(self, selection_input: SelectionInput) -> SelectionResult:
        # Keep prompt builder reachable for future wiring
        _ = build_selection_prompt(
            selection_input.question,
            [c.to_dict() for c in selection_input.candidates],
        )
        result = self._fallback.select(selection_input)
        result.selector = self.name
        result.reason = (
            f"[LLM selector placeholder — used rule-based choice] {result.reason}"
        )
        logger.info(
            "LLMDatasetSelector placeholder used rule-based result",
            extra={"best": result.best_dataset.candidate_id if result.best_dataset else None},
        )
        return result


_default_selector: DatasetSelector | None = None


def get_default_selector() -> DatasetSelector:
    global _default_selector
    if _default_selector is None:
        _default_selector = RuleBasedSelector()
    return _default_selector


def set_default_selector(selector: DatasetSelector) -> None:
    global _default_selector
    _default_selector = selector


def select_best_dataset(
    question: str,
    candidates: list[Any],
    *,
    topic: str = "",
    selector: DatasetSelector | None = None,
) -> SelectionResult:
    """
    Public entrypoint for Retrieval (to be wired later):

        select_best_dataset(user_question, top_candidates)
    """
    impl = selector or get_default_selector()
    return impl.select_best_dataset(question, candidates, topic=topic)
