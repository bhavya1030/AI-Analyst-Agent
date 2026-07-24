"""Resolve linguistic references against conversation context.

Examples: it, them, same dataset, previous chart, that country,
last analysis, same filter.
"""

from __future__ import annotations

import re
from typing import Optional

from backend.context.models import (
    ConversationContext,
    ReferenceKind,
    ResolvedReference,
    ResolvedRequest,
)
from backend.core.logger import get_logger

logger = get_logger(__name__)

# Phrase patterns ordered from longer / more specific to shorter
_PHRASE_PATTERNS: list[tuple[re.Pattern[str], ReferenceKind]] = [
    (re.compile(r"\bprevious\s+chart\b", re.I), ReferenceKind.PREVIOUS_CHART),
    (re.compile(r"\blast\s+chart\b", re.I), ReferenceKind.PREVIOUS_CHART),
    (re.compile(r"\bthat\s+chart\b", re.I), ReferenceKind.PREVIOUS_CHART),
    (re.compile(r"\bsame\s+dataset\b", re.I), ReferenceKind.SAME_DATASET),
    (re.compile(r"\bthe\s+same\s+dataset\b", re.I), ReferenceKind.SAME_DATASET),
    (re.compile(r"\bthis\s+dataset\b", re.I), ReferenceKind.SAME_DATASET),
    (re.compile(r"\bthe\s+dataset\b", re.I), ReferenceKind.SAME_DATASET),
    (re.compile(r"\bthe\s+data\b", re.I), ReferenceKind.SAME_DATASET),
    (re.compile(r"\blast\s+analysis\b", re.I), ReferenceKind.LAST_ANALYSIS),
    (re.compile(r"\bprevious\s+analysis\b", re.I), ReferenceKind.LAST_ANALYSIS),
    (re.compile(r"\bsame\s+filter\b", re.I), ReferenceKind.SAME_FILTER),
    (re.compile(r"\bthe\s+same\s+filter\b", re.I), ReferenceKind.SAME_FILTER),
    (re.compile(r"\bthat\s+filter\b", re.I), ReferenceKind.SAME_FILTER),
    (re.compile(r"\bthat\s+country\b", re.I), ReferenceKind.THAT_COUNTRY),
    (re.compile(r"\bthe\s+same\s+country\b", re.I), ReferenceKind.THAT_COUNTRY),
    (re.compile(r"\bsame\s+country\b", re.I), ReferenceKind.THAT_COUNTRY),
    (re.compile(r"\bthose\s+countries\b", re.I), ReferenceKind.THAT_COUNTRY),
    (re.compile(r"\bprevious\s+years?\b", re.I), ReferenceKind.PREVIOUS_YEARS),
    (re.compile(r"\bsame\s+metric\b", re.I), ReferenceKind.ACTIVE_METRIC),
    (re.compile(r"\bthat\s+metric\b", re.I), ReferenceKind.ACTIVE_METRIC),
    (re.compile(r"\bthe\s+metric\b", re.I), ReferenceKind.ACTIVE_METRIC),
    # Pronouns last
    (re.compile(r"\bthem\b", re.I), ReferenceKind.THEM),
    (re.compile(r"\bthose\b", re.I), ReferenceKind.THEM),
    (re.compile(r"\bthat\b", re.I), ReferenceKind.THAT),
    (re.compile(r"\bthis\b", re.I), ReferenceKind.THIS),
    (re.compile(r"\bit\b", re.I), ReferenceKind.IT),
]

# Standalone follow-up templates (full or near-full phrase match)
_FOLLOW_UP_TEMPLATES: list[tuple[re.Pattern[str], str, ReferenceKind]] = [
    (
        re.compile(r"^(explain|describe)\s+(that|this|it)\b", re.I),
        "explain {subject}",
        ReferenceKind.IT,
    ),
    (
        re.compile(r"^(forecast|predict)\s+(it|that|this)\b", re.I),
        "forecast {subject}",
        ReferenceKind.IT,
    ),
    (
        re.compile(r"^(plot|visualize|show|chart)\s+(it|that|this)\b", re.I),
        "visualize {subject}",
        ReferenceKind.IT,
    ),
    (
        re.compile(r"^compare\s+(it|that|this)\s+with\b", re.I),
        "compare {subject} with",
        ReferenceKind.IT,
    ),
    (
        re.compile(r"^analyze\s+(it|that|this)\b", re.I),
        "analyze {subject}",
        ReferenceKind.IT,
    ),
]


class ReferenceResolver:
    """Resolve pronouns and contextual phrases using ConversationContext."""

    def resolve(
        self,
        question: str,
        context: ConversationContext | None,
        *,
        conversation_id: str = "",
    ) -> ResolvedRequest:
        original = (question or "").strip()
        cid = conversation_id or (context.conversation_id if context else "") or ""

        if not original:
            return ResolvedRequest(
                conversation_id=cid,
                original_question="",
                resolved_question="",
                warnings=["Empty question"],
            )

        if context is None:
            return ResolvedRequest(
                conversation_id=cid,
                original_question=original,
                resolved_question=original,
                is_follow_up=False,
                reuse_active_dataset=False,
            )

        subject = self._subject(context)
        refs: list[ResolvedReference] = []
        resolved = original
        warnings: list[str] = []

        # 1) Template-level rewrites
        for pattern, template, kind in _FOLLOW_UP_TEMPLATES:
            m = pattern.search(resolved)
            if not m:
                continue
            value = subject or m.group(0)
            if not subject:
                warnings.append(f"No subject available to resolve '{m.group(0)}'")
                break
            rewritten = template.format(subject=subject)
            # Preserve trailing text after the matched prefix
            trailing = resolved[m.end() :].strip()
            if trailing and not rewritten.rstrip().endswith(trailing):
                # e.g. "compare it with China" → "compare India GDP with" + "China"
                if rewritten.endswith(" with") and trailing.lower().startswith("with "):
                    trailing = trailing[5:].strip()
                resolved = f"{rewritten} {trailing}".strip() if trailing else rewritten
            else:
                resolved = rewritten
            refs.append(
                ResolvedReference(
                    kind=kind,
                    original_span=m.group(0),
                    resolved_value=subject,
                    detail={"template": template},
                )
            )
            break

        # 2) Phrase / pronoun substitution (left-to-right, non-overlapping-ish)
        resolved, phrase_refs = self._replace_phrases(resolved, context, subject)
        refs.extend(phrase_refs)

        is_follow_up = bool(refs) or self._looks_like_follow_up(original)
        reuse = bool(context.active_dataset()) and (
            is_follow_up or self._mentions_same_dataset(original)
        )

        if is_follow_up and not subject:
            warnings.append("Follow-up detected but no active dataset/topic in context")

        # Special: "compare it with China" style — subject already applied
        # Ensure filters / countries / chart refs attached
        countries = list(context.selected_countries)
        metrics = list(context.metrics)
        filters = list(context.filters)

        # If user said "same filter" we already replaced text; keep filters attached
        if any(r.kind == ReferenceKind.SAME_FILTER for r in refs) and not filters:
            warnings.append("Referenced same filter but no filters stored in context")

        if any(r.kind == ReferenceKind.PREVIOUS_CHART for r in refs) and not context.last_chart():
            warnings.append("Referenced previous chart but none stored in context")

        return ResolvedRequest(
            conversation_id=cid,
            original_question=original,
            resolved_question=resolved,
            is_follow_up=is_follow_up,
            reuse_active_dataset=reuse,
            dataset_refs=list(context.active_datasets),
            filters=filters,
            countries=countries,
            metrics=metrics,
            last_chart=context.last_chart(),
            last_analysis=context.last_analysis(),
            resolved_references=refs,
            primary_topic=context.primary_topic(),
            last_operation=context.last_operation,
            last_intent=context.last_intent,
            warnings=warnings,
            metadata={
                "subject": subject,
                "had_context": True,
            },
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _subject(self, context: ConversationContext) -> str:
        topic = context.primary_topic()
        if topic:
            return topic
        if context.selected_countries and context.metrics:
            return f"{context.selected_countries[0]} {context.metrics[0]}"
        if context.selected_countries:
            return context.selected_countries[0]
        if context.metrics:
            return context.metrics[0]
        if context.last_columns:
            return str(context.last_columns[-1])
        if context.last_forecast_target:
            return context.last_forecast_target
        step = context.last_analysis()
        if step and step.resolved_question:
            return step.resolved_question
        if step and step.question:
            return step.question
        return ""

    def _replace_phrases(
        self,
        text: str,
        context: ConversationContext,
        subject: str,
    ) -> tuple[str, list[ResolvedReference]]:
        refs: list[ResolvedReference] = []
        result = text
        # Track replaced spans by working on a lowercase mask to avoid double-replace
        occupied = [False] * len(result)

        for pattern, kind in _PHRASE_PATTERNS:
            for match in pattern.finditer(result):
                start, end = match.start(), match.end()
                if any(occupied[start:end]):
                    continue
                value = self._value_for_kind(kind, context, subject, match.group(0))
                if not value:
                    continue
                # Build replacement carefully
                # For pronouns substitute subject; for structured refs may expand phrase
                replacement = value
                if kind in {
                    ReferenceKind.PREVIOUS_CHART,
                    ReferenceKind.LAST_ANALYSIS,
                    ReferenceKind.SAME_FILTER,
                }:
                    # Keep readable phrase with detail
                    replacement = value

                # Apply replacement on result
                result = result[:start] + replacement + result[end:]
                # Rebuild occupied for new length — restart scan for this pattern
                delta = len(replacement) - (end - start)
                # Mark occupied region for the replacement
                new_occupied = [False] * len(result)
                # Simple approach: recompute from refs already applied by re-running
                # from scratch is expensive; instead mark approx region
                for i in range(start, min(start + len(replacement), len(result))):
                    new_occupied[i] = True
                # Shift previous occupied
                for i, flag in enumerate(occupied):
                    if not flag:
                        continue
                    if i < start:
                        new_occupied[i] = True
                    elif i >= end:
                        ni = i + delta
                        if 0 <= ni < len(new_occupied):
                            new_occupied[ni] = True
                occupied = new_occupied

                refs.append(
                    ResolvedReference(
                        kind=kind,
                        original_span=match.group(0),
                        resolved_value=value,
                    )
                )
                # Only first match per pattern pass; continue to next pattern
                break

        return result, refs

    def _value_for_kind(
        self,
        kind: ReferenceKind,
        context: ConversationContext,
        subject: str,
        span: str,
    ) -> str:
        if kind in {ReferenceKind.IT, ReferenceKind.THIS, ReferenceKind.THAT, ReferenceKind.THEM}:
            return subject
        if kind == ReferenceKind.SAME_DATASET:
            ds = context.active_dataset()
            return (ds.topic if ds and ds.topic else subject) or "the active dataset"
        if kind == ReferenceKind.PREVIOUS_CHART:
            chart = context.last_chart()
            if not chart:
                return ""
            parts = []
            if chart.chart_type:
                parts.append(chart.chart_type)
            if chart.columns:
                parts.append("of " + ", ".join(chart.columns))
            if chart.title:
                parts.append(f'("{chart.title}")')
            return " ".join(parts).strip() or "the previous chart"
        if kind == ReferenceKind.THAT_COUNTRY:
            if context.selected_countries:
                if kind == ReferenceKind.THAT_COUNTRY and "countries" in span.lower():
                    return ", ".join(context.selected_countries)
                return context.selected_countries[-1]
            # Infer from topic e.g. "India GDP"
            topic = context.primary_topic()
            for token in topic.replace(",", " ").split():
                if token[:1].isupper() and token.lower() not in {
                    "gdp", "cpi", "usd", "api", "eda",
                }:
                    return token
            return subject
        if kind == ReferenceKind.LAST_ANALYSIS:
            step = context.last_analysis()
            if not step:
                return ""
            return step.summary or step.resolved_question or step.question or step.operation
        if kind == ReferenceKind.SAME_FILTER:
            if not context.filters:
                return ""
            labels = [f.label or f"{f.column} {f.operator} {f.value}" for f in context.filters]
            return "; ".join(labels)
        if kind == ReferenceKind.PREVIOUS_YEARS:
            for f in context.filters:
                if f.column.lower() in {"year", "date"} and f.value is not None:
                    return f.label or f"{f.column} {f.operator} {f.value}"
            return subject
        if kind == ReferenceKind.ACTIVE_METRIC:
            if context.metrics:
                return context.metrics[-1]
            if context.last_columns:
                return context.last_columns[-1]
            return subject
        return subject

    @staticmethod
    def _looks_like_follow_up(question: str) -> bool:
        q = question.lower().strip()
        if len(q.split()) <= 12 and re.search(
            r"\b(it|that|this|them|those|same|previous|last)\b", q
        ):
            return True
        if re.search(r"\b(same dataset|previous chart|last analysis|same filter)\b", q):
            return True
        return False

    @staticmethod
    def _mentions_same_dataset(question: str) -> bool:
        return bool(
            re.search(r"\b(same dataset|this dataset|the dataset|the data)\b", question, re.I)
        )
