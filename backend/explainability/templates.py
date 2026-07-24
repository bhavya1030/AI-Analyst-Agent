"""Text templates for short / detailed / technical explanations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from backend.explainability.models import (
        DatasetCitation,
        ExplanationResult,
        FilterExplanation,
        JoinExplanation,
        ToolStepExplanation,
    )


def render_short(
    *,
    question: str,
    summary: str,
    dataset_names: Sequence[str],
    tool_names: Sequence[str],
    confidence: float,
    warning_count: int,
) -> str:
    parts: list[str] = []
    if summary:
        parts.append(summary.strip())
    else:
        parts.append("Answer produced from available analytical pipeline outputs.")
    if dataset_names:
        parts.append(f"Data: {', '.join(dataset_names[:4])}.")
    if tool_names:
        parts.append(f"Methods: {', '.join(tool_names[:4])}.")
    parts.append(f"Confidence: {_pct(confidence)}.")
    if warning_count:
        parts.append(f"{warning_count} warning(s).")
    return " ".join(parts)


def render_detailed(
    *,
    question: str,
    summary: str,
    reasoning: str,
    datasets: Sequence["DatasetCitation"],
    sources: Sequence[str],
    columns: Sequence[str],
    filters: Sequence["FilterExplanation"],
    joins: "JoinExplanation | None",
    tools: Sequence["ToolStepExplanation"],
    confidence: float,
    warnings: Sequence[str],
    limitations: Sequence[str],
    citations: Sequence["DatasetCitation"],
) -> str:
    lines: list[str] = []
    lines.append("## How this answer was produced")
    if question:
        lines.append(f"**Question:** {question}")
    if summary:
        lines.append(f"**Summary:** {summary}")
    if reasoning:
        lines.append("")
        lines.append("### Reasoning")
        lines.append(reasoning)

    lines.append("")
    lines.append("### Datasets used")
    if datasets:
        for i, d in enumerate(datasets, 1):
            label = d.citation_label or d.topic or d.dataset_id or f"Dataset {i}"
            src = d.source or d.provider or "unknown source"
            lines.append(f"{i}. **{label}** — source: {src}")
            if d.source_url:
                lines.append(f"   - URL: {d.source_url}")
            if d.columns:
                lines.append(f"   - Columns: {', '.join(d.columns[:12])}")
    else:
        lines.append("_No dataset metadata provided._")

    if sources:
        lines.append("")
        lines.append("### Sources")
        for s in sources:
            lines.append(f"- {s}")

    if columns:
        lines.append("")
        lines.append("### Columns used")
        lines.append(", ".join(columns[:30]))

    if filters:
        lines.append("")
        lines.append("### Filters applied")
        for f in filters:
            label = f.label or f"{f.column} {f.operator} {f.value}".strip()
            lines.append(f"- {label}")

    if joins and (joins.strategy or joins.join_keys or joins.datasets_merged):
        lines.append("")
        lines.append("### Joins performed")
        if joins.strategy:
            lines.append(f"- Strategy: `{joins.strategy}`")
        if joins.join_keys:
            lines.append(f"- Keys: {', '.join(joins.join_keys)}")
        if joins.datasets_merged:
            lines.append(f"- Datasets merged: {joins.datasets_merged}")
        for n in joins.notes[:5]:
            lines.append(f"- Note: {n}")

    if tools:
        lines.append("")
        lines.append("### Analytical tools executed")
        for t in sorted(tools, key=lambda x: x.order or 0):
            name = t.name or t.tool_id or "tool"
            order = f"{t.order}. " if t.order else "- "
            extra = f" — {t.reason}" if t.reason else ""
            lines.append(f"{order}**{name}**{extra}")

    lines.append("")
    lines.append(f"### Confidence: {_pct(confidence)}")

    if warnings:
        lines.append("")
        lines.append("### Warnings")
        for w in warnings:
            lines.append(f"- {w}")

    if limitations:
        lines.append("")
        lines.append("### Limitations")
        for lim in limitations:
            lines.append(f"- {lim}")

    if citations:
        lines.append("")
        lines.append("### Citations")
        for i, c in enumerate(citations, 1):
            label = c.citation_label or _default_citation_label(i, c)
            lines.append(f"[{i}] {label}")

    return "\n".join(lines).strip()


def render_technical(
    *,
    question: str,
    summary: str,
    reasoning: str,
    datasets: Sequence["DatasetCitation"],
    sources: Sequence[str],
    columns: Sequence[str],
    filters: Sequence["FilterExplanation"],
    joins: "JoinExplanation | None",
    tools: Sequence["ToolStepExplanation"],
    confidence: float,
    warnings: Sequence[str],
    limitations: Sequence[str],
    citations: Sequence["DatasetCitation"],
    metadata: dict | None = None,
) -> str:
    """Machine-oriented technical explanation with explicit field blocks."""
    lines: list[str] = []
    lines.append("# Technical Explanation")
    lines.append(f"question: {question or 'n/a'}")
    lines.append(f"summary: {summary or 'n/a'}")
    lines.append(f"confidence: {confidence:.4f}")
    lines.append("")
    lines.append("## reasoning")
    lines.append(reasoning or "n/a")
    lines.append("")
    lines.append("## datasets")
    if not datasets:
        lines.append("(none)")
    for i, d in enumerate(datasets, 1):
        lines.append(f"[{i}] topic={d.topic!r} id={d.dataset_id!r} source={d.source!r}")
        lines.append(f"    provider={d.provider!r} url={d.source_url!r}")
        lines.append(f"    path={d.local_path!r} rows={d.row_count}")
        if d.columns:
            lines.append(f"    columns={list(d.columns)[:40]}")
    lines.append("")
    lines.append("## sources")
    lines.append(", ".join(sources) if sources else "(none)")
    lines.append("")
    lines.append("## columns_used")
    lines.append(", ".join(columns) if columns else "(none)")
    lines.append("")
    lines.append("## filters")
    if not filters:
        lines.append("(none)")
    for f in filters:
        lines.append(
            f"- column={f.column!r} op={f.operator!r} value={f.value!r} label={f.label!r}"
        )
    lines.append("")
    lines.append("## joins")
    if joins:
        lines.append(f"strategy={joins.strategy!r}")
        lines.append(f"keys={list(joins.join_keys)}")
        lines.append(f"datasets_merged={joins.datasets_merged}")
        if joins.schema_alignment:
            keys = joins.schema_alignment.get("join_keys") or joins.join_keys
            lines.append(f"schema_join_keys={keys}")
            rename = joins.schema_alignment.get("rename_maps")
            if rename:
                lines.append(f"rename_maps_count={len(rename)}")
        for n in joins.notes:
            lines.append(f"note: {n}")
    else:
        lines.append("(none)")
    lines.append("")
    lines.append("## tools")
    if not tools:
        lines.append("(none)")
    for t in sorted(tools, key=lambda x: x.order or 0):
        lines.append(
            f"{t.order or '-'} id={t.tool_id!r} name={t.name!r} "
            f"category={t.category!r} chart={t.produces_chart}"
        )
        if t.reason:
            lines.append(f"    reason: {t.reason}")
    lines.append("")
    lines.append("## warnings")
    if not warnings:
        lines.append("(none)")
    for w in warnings:
        lines.append(f"- {w}")
    lines.append("")
    lines.append("## limitations")
    if not limitations:
        lines.append("(none)")
    for lim in limitations:
        lines.append(f"- {lim}")
    lines.append("")
    lines.append("## citations")
    if not citations:
        lines.append("(none)")
    for i, c in enumerate(citations, 1):
        lines.append(
            f"[{i}] {c.citation_label or c.topic} | {c.source or c.provider} | {c.source_url or c.local_path}"
        )
    if metadata:
        lines.append("")
        lines.append("## metadata_keys")
        lines.append(", ".join(sorted(str(k) for k in metadata.keys())[:40]))
    return "\n".join(lines).strip()


def build_reasoning_summary(
    *,
    question: str,
    dataset_names: Sequence[str],
    tool_names: Sequence[str],
    join_strategy: str,
    join_keys: Sequence[str],
    filter_labels: Sequence[str],
    analysis_snippet: str,
) -> str:
    bits: list[str] = []
    if question:
        bits.append(f"The user asked: “{question.strip()}”.")
    if dataset_names:
        bits.append(
            f"Analysis used {len(dataset_names)} dataset(s): {', '.join(dataset_names)}."
        )
    else:
        bits.append("No explicit dataset metadata was attached to the result.")
    if join_strategy:
        key_txt = f" on {', '.join(join_keys)}" if join_keys else ""
        bits.append(f"Datasets were combined using `{join_strategy}`{key_txt}.")
    if filter_labels:
        bits.append("Filters applied: " + "; ".join(filter_labels) + ".")
    if tool_names:
        bits.append(
            "Analytical steps included: " + ", ".join(tool_names) + "."
        )
    if analysis_snippet:
        bits.append(f"Result snapshot: {analysis_snippet}")
    bits.append(
        "This explanation is derived from pipeline metadata (datasets, plan, joins, tools), "
        "not from re-running the analysis."
    )
    return " ".join(bits)


def build_limitations(
    *,
    has_datasets: bool,
    has_tools: bool,
    has_joins: bool,
    warnings: Sequence[str],
    multi_dataset: bool,
    confidence: float,
) -> list[str]:
    limits: list[str] = []
    if not has_datasets:
        limits.append("Dataset provenance was incomplete; citations may be partial.")
    if not has_tools:
        limits.append("No explicit tool execution plan was provided; methods may be incomplete.")
    if multi_dataset and not has_joins:
        limits.append("Multiple datasets were used but join strategy was not specified.")
    if confidence < 0.4:
        limits.append("Low confidence — treat findings as provisional.")
    if warnings:
        limits.append("Pipeline reported warnings that may affect reliability.")
    limits.append(
        "Correlation or observed patterns do not by themselves imply causation."
    )
    limits.append(
        "Results depend on data quality, coverage, and any filters applied upstream."
    )
    return limits


def _default_citation_label(index: int, c: "DatasetCitation") -> str:
    parts = []
    if c.source:
        parts.append(str(c.source))
    if c.topic:
        parts.append(str(c.topic))
    elif c.dataset_id:
        parts.append(str(c.dataset_id))
    if c.source_url:
        parts.append(str(c.source_url))
    body = " — ".join(parts) if parts else f"Dataset {index}"
    return body


def _pct(confidence: float) -> str:
    try:
        return f"{max(0.0, min(1.0, float(confidence))) * 100:.0f}%"
    except (TypeError, ValueError):
        return "n/a"


def build_llm_explanation_prompt(payload: dict) -> str:
    """Prompt for future LLMExplainer — not used by rule-based path."""
    import json

    return f"""You are an explainability assistant for an analytics copilot.

Given structured pipeline metadata, write a clear explanation of HOW the answer
was produced (not a new analysis).

Include:
- datasets and sources
- columns and filters
- joins
- analytical tools
- reasoning summary
- confidence
- warnings and limitations
- citations

Return ONLY valid JSON:
{{
  "summary": "...",
  "reasoning_summary": "...",
  "short_text": "...",
  "detailed_text": "...",
  "technical_text": "...",
  "limitations": ["..."],
  "confidence": 0.0
}}

Input metadata:
{json.dumps(payload, indent=2, ensure_ascii=False)[:8000]}
"""
