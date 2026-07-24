"""Explainability Layer — structured reasoning for analytical answers.

Explainer ABC
  └─ RuleBasedExplainer  (default)
  └─ LLMExplainer        (placeholder / optional)

Does not modify Planner, EDA, Visualization, or Insight generation.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from backend.core.logger import get_logger
from backend.explainability.models import (
    DatasetCitation,
    ExplanationInput,
    ExplanationResult,
    ExplanationStyle,
    FilterExplanation,
    JoinExplanation,
    ToolStepExplanation,
)
from backend.explainability.templates import (
    build_limitations,
    build_llm_explanation_prompt,
    build_reasoning_summary,
    render_detailed,
    render_short,
    render_technical,
)

logger = get_logger(__name__)


class Explainer(ABC):
    """Generate structured explanations of how an answer was produced."""

    name: str = "base"

    @abstractmethod
    def explain(self, explanation_input: ExplanationInput) -> ExplanationResult:
        ...

    def generate_explanation(
        self,
        *,
        analysis_result: Any = None,
        execution_plan: Any = None,
        datasets_used: Any = None,
        join_plan: Any = None,
        question: str = "",
        style: Any = ExplanationStyle.DETAILED,
        **kwargs: Any,
    ) -> ExplanationResult:
        """Primary API — stable for callers when swapping RuleBased → LLM."""
        inp = ExplanationInput.from_raw(
            question=question,
            analysis_result=analysis_result,
            execution_plan=execution_plan,
            datasets_used=datasets_used,
            join_plan=join_plan,
            style=style,
            **kwargs,
        )
        return self.explain(inp)


class RuleBasedExplainer(Explainer):
    """Deterministic explanation builder from pipeline metadata."""

    name = "rule_based"

    def explain(self, explanation_input: ExplanationInput) -> ExplanationResult:
        inp = explanation_input
        style = inp.style if isinstance(inp.style, ExplanationStyle) else ExplanationStyle.DETAILED

        datasets = self._extract_datasets(inp)
        citations = self._build_citations(datasets)
        sources = self._extract_sources(datasets, inp)
        columns = self._extract_columns(inp, datasets)
        filters = self._extract_filters(inp)
        joins = self._extract_joins(inp)
        tools = self._extract_tools(inp)
        warnings = self._collect_warnings(inp)
        confidence = self._compute_confidence(inp, datasets, tools, warnings)
        analysis_snippet = self._analysis_snippet(inp.analysis_result)
        summary = self._build_summary(inp, datasets, tools, analysis_snippet)

        dataset_names = [d.topic or d.dataset_id or "dataset" for d in datasets]
        tool_names = [t.name or t.tool_id for t in tools if (t.name or t.tool_id)]
        filter_labels = [
            f.label or f"{f.column} {f.operator} {f.value}".strip() for f in filters
        ]

        reasoning = build_reasoning_summary(
            question=inp.question,
            dataset_names=dataset_names,
            tool_names=tool_names,
            join_strategy=joins.strategy if joins else "",
            join_keys=joins.join_keys if joins else [],
            filter_labels=filter_labels,
            analysis_snippet=analysis_snippet,
        )

        limitations = build_limitations(
            has_datasets=bool(datasets),
            has_tools=bool(tools),
            has_joins=bool(joins and (joins.strategy or joins.join_keys)),
            warnings=warnings,
            multi_dataset=len(datasets) > 1,
            confidence=confidence,
        )

        short_text = render_short(
            question=inp.question,
            summary=summary,
            dataset_names=dataset_names,
            tool_names=tool_names,
            confidence=confidence,
            warning_count=len(warnings),
        )
        detailed_text = render_detailed(
            question=inp.question,
            summary=summary,
            reasoning=reasoning,
            datasets=datasets,
            sources=sources,
            columns=columns,
            filters=filters,
            joins=joins,
            tools=tools,
            confidence=confidence,
            warnings=warnings,
            limitations=limitations,
            citations=citations,
        )
        technical_text = render_technical(
            question=inp.question,
            summary=summary,
            reasoning=reasoning,
            datasets=datasets,
            sources=sources,
            columns=columns,
            filters=filters,
            joins=joins,
            tools=tools,
            confidence=confidence,
            warnings=warnings,
            limitations=limitations,
            citations=citations,
            metadata=inp.metadata,
        )

        explanation_text = {
            ExplanationStyle.SHORT: short_text,
            ExplanationStyle.DETAILED: detailed_text,
            ExplanationStyle.TECHNICAL: technical_text,
        }.get(style, detailed_text)

        result = ExplanationResult(
            style=style,
            summary=summary,
            datasets_used=datasets,
            sources=sources,
            columns_used=columns,
            filters_applied=filters,
            joins_performed=joins,
            tools_executed=tools,
            reasoning_summary=reasoning,
            confidence=confidence,
            warnings=warnings,
            limitations=limitations,
            citations=citations,
            short_text=short_text,
            detailed_text=detailed_text,
            technical_text=technical_text,
            explanation_text=explanation_text,
            explainer=self.name,
            question=inp.question,
            metadata={
                "n_datasets": len(datasets),
                "n_tools": len(tools),
                "n_filters": len(filters),
                **dict(inp.metadata or {}),
            },
        )
        logger.info(
            "Explanation generated",
            extra={
                "style": style.value,
                "confidence": confidence,
                "n_datasets": len(datasets),
                "n_tools": len(tools),
            },
        )
        return result

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract_datasets(self, inp: ExplanationInput) -> list[DatasetCitation]:
        raw_list = list(inp.datasets_used or [])

        # From execution / analysis result envelopes
        for blob in (inp.analysis_result, inp.execution_plan, inp.join_plan):
            if not blob:
                continue
            for key in (
                "datasets_used",
                "datasets_processed",
                "datasets",
                "dataset_refs",
                "active_datasets",
            ):
                if key in blob and blob[key]:
                    items = blob[key]
                    if isinstance(items, list):
                        raw_list.extend(
                            x if isinstance(x, dict) else {"value": str(x)} for x in items
                        )
                    elif isinstance(items, dict):
                        raw_list.append(items)

            # Single dataset metadata
            for key in ("dataset_metadata", "metadata"):
                meta = blob.get(key)
                if isinstance(meta, dict) and (
                    meta.get("topic") or meta.get("local_path") or meta.get("dataset_id")
                ):
                    raw_list.append(meta)

        # Deduplicate by topic/id/path
        seen: set[str] = set()
        out: list[DatasetCitation] = []
        for i, raw in enumerate(raw_list):
            if not isinstance(raw, dict):
                continue
            cit = DatasetCitation.from_dict(raw)
            # Enrich from nested retrieval/acquisition if present
            if not cit.topic and raw.get("retrieval"):
                r = raw["retrieval"] if isinstance(raw["retrieval"], dict) else {}
                cit.topic = str(r.get("topic") or cit.topic)
                cit.dataset_id = cit.dataset_id or r.get("dataset_id")
                cit.provider = cit.provider or r.get("provider")
            if not cit.local_path and raw.get("local_path"):
                cit.local_path = str(raw["local_path"])
            if not cit.columns and raw.get("profile"):
                prof = raw["profile"] if isinstance(raw["profile"], dict) else {}
                cit.columns = [str(c) for c in (prof.get("column_names") or [])]
                if cit.row_count is None:
                    cit.row_count = prof.get("row_count")
            key = (
                (cit.dataset_id or "")
                + "|"
                + (cit.topic or "")
                + "|"
                + (cit.local_path or "")
            ).lower()
            if key.strip("|") == "" or key in seen:
                if key.strip("|") == "":
                    continue
                continue
            seen.add(key)
            if not cit.citation_label:
                cit.citation_label = self._citation_label(len(out) + 1, cit)
            out.append(cit)
        return out

    def _build_citations(self, datasets: list[DatasetCitation]) -> list[DatasetCitation]:
        # Citations mirror datasets with labels; filter to those with some provenance
        citations: list[DatasetCitation] = []
        for i, d in enumerate(datasets):
            if d.source or d.source_url or d.provider or d.dataset_id or d.topic:
                c = DatasetCitation(
                    topic=d.topic,
                    dataset_id=d.dataset_id,
                    source=d.source,
                    source_url=d.source_url,
                    local_path=d.local_path,
                    provider=d.provider,
                    columns=list(d.columns),
                    row_count=d.row_count,
                    citation_label=d.citation_label or self._citation_label(i + 1, d),
                    metadata=dict(d.metadata),
                )
                citations.append(c)
        return citations

    def _extract_sources(
        self, datasets: list[DatasetCitation], inp: ExplanationInput
    ) -> list[str]:
        sources: list[str] = []
        for d in datasets:
            label = d.source or d.provider
            if label and label not in sources:
                sources.append(str(label))
            if d.source_url and d.source_url not in sources:
                sources.append(str(d.source_url))
        # analysis result sources
        ar = inp.analysis_result or {}
        for key in ("source", "dataset_source", "sources"):
            val = ar.get(key)
            if isinstance(val, str) and val and val not in sources:
                sources.append(val)
            elif isinstance(val, list):
                for s in val:
                    if s and str(s) not in sources:
                        sources.append(str(s))
        return sources

    def _extract_columns(
        self, inp: ExplanationInput, datasets: list[DatasetCitation]
    ) -> list[str]:
        cols: list[str] = list(inp.columns_used or [])
        for blob in (inp.analysis_result, inp.execution_plan):
            if not blob:
                continue
            for key in (
                "columns_used",
                "last_columns",
                "last_columns_used",
                "chart_columns_used",
                "columns",
                "merged_columns",
            ):
                val = blob.get(key)
                if isinstance(val, list):
                    cols.extend(str(c) for c in val)
            # profile
            prof = blob.get("dataset_intelligence") or blob.get("profile")
            if isinstance(prof, dict) and prof.get("column_names"):
                cols.extend(str(c) for c in prof["column_names"])
        if not cols:
            for d in datasets:
                cols.extend(d.columns)
        # unique preserve order
        seen: set[str] = set()
        out: list[str] = []
        for c in cols:
            if c and c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def _extract_filters(self, inp: ExplanationInput) -> list[FilterExplanation]:
        raw = list(inp.filters or [])
        for blob in (inp.analysis_result, inp.execution_plan):
            if not blob:
                continue
            for key in ("filters", "filters_applied", "active_filters"):
                val = blob.get(key)
                if isinstance(val, list):
                    raw.extend(x for x in val if isinstance(x, dict))
                elif isinstance(val, dict):
                    raw.append(val)
        out: list[FilterExplanation] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(FilterExplanation.from_dict(item))
            elif isinstance(item, str):
                out.append(FilterExplanation(label=item))
        return out

    def _extract_joins(self, inp: ExplanationInput) -> Optional[JoinExplanation]:
        candidates: list[dict[str, Any]] = []
        if inp.join_plan:
            candidates.append(inp.join_plan)
        for blob in (inp.analysis_result, inp.execution_plan):
            if not blob:
                continue
            if any(
                k in blob
                for k in ("join_strategy", "join_keys", "strategy", "datasets_merged")
            ):
                candidates.append(blob)
            nested = blob.get("join_plan") or blob.get("merge_result") or blob.get("join")
            if isinstance(nested, dict):
                candidates.append(nested)

        if not candidates:
            return None

        # Merge fields from first non-empty
        strategy = ""
        keys: list[str] = []
        merged = 0
        notes: list[str] = []
        schema = None
        for c in candidates:
            strategy = strategy or str(
                c.get("strategy") or c.get("join_strategy") or ""
            )
            if not keys and c.get("join_keys"):
                keys = [str(k) for k in c["join_keys"]]
            if not merged:
                merged = int(c.get("datasets_merged") or 0)
            for n in c.get("notes") or c.get("warnings") or []:
                notes.append(str(n))
            if schema is None and c.get("schema_alignment"):
                schema = c.get("schema_alignment")
            # local_paths count as merged hint
            if not merged and c.get("local_paths"):
                try:
                    merged = len(c["local_paths"])
                except Exception:
                    pass
            if not merged and c.get("topics_succeeded"):
                try:
                    merged = len(c["topics_succeeded"])
                except Exception:
                    pass

        if not strategy and not keys and not merged:
            return None
        return JoinExplanation(
            strategy=strategy,
            join_keys=keys,
            datasets_merged=merged,
            notes=list(dict.fromkeys(notes))[:10],
            schema_alignment=schema if isinstance(schema, dict) else None,
        )

    def _extract_tools(self, inp: ExplanationInput) -> list[ToolStepExplanation]:
        raw = list(inp.tools_executed or [])
        plan = inp.execution_plan or {}
        if plan.get("selected_tools"):
            raw.extend(x for x in plan["selected_tools"] if isinstance(x, dict))
        if plan.get("tools"):
            for t in plan["tools"]:
                if isinstance(t, dict):
                    raw.append(t)
                elif isinstance(t, str):
                    raw.append({"tool_id": t, "name": t})
        if plan.get("tool_ids") and isinstance(plan["tool_ids"], list):
            existing = {str(r.get("tool_id") or r.get("name")) for r in raw if isinstance(r, dict)}
            for i, tid in enumerate(plan["tool_ids"]):
                if str(tid) not in existing:
                    raw.append({"tool_id": str(tid), "name": str(tid), "order": i + 1})

        # analysis result plan / steps
        ar = inp.analysis_result or {}
        for key in ("plan", "tools_executed", "selected_tools", "steps"):
            val = ar.get(key)
            if isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, dict):
                        raw.append(item)
                    elif isinstance(item, str):
                        raw.append({"tool_id": item, "name": item, "order": i + 1})

        out: list[ToolStepExplanation] = []
        seen: set[str] = set()
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            step = ToolStepExplanation.from_dict(item)
            if not step.order:
                step.order = i + 1
            key = (step.tool_id or step.name or str(i)).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(step)
        out.sort(key=lambda t: t.order or 0)
        return out

    def _collect_warnings(self, inp: ExplanationInput) -> list[str]:
        warnings = list(inp.warnings or [])
        for blob in (inp.analysis_result, inp.execution_plan, inp.join_plan):
            if not blob:
                continue
            for w in blob.get("warnings") or []:
                warnings.append(str(w))
            for e in blob.get("errors") or []:
                warnings.append(f"error: {e}")
        # Dedup
        return list(dict.fromkeys(w for w in warnings if w))

    def _compute_confidence(
        self,
        inp: ExplanationInput,
        datasets: list[DatasetCitation],
        tools: list[ToolStepExplanation],
        warnings: list[str],
    ) -> float:
        if inp.confidence is not None:
            return max(0.0, min(1.0, float(inp.confidence)))

        score = 0.35
        # From execution plan confidence
        plan = inp.execution_plan or {}
        if plan.get("confidence") is not None:
            try:
                score = max(score, float(plan["confidence"]))
            except (TypeError, ValueError):
                pass
        ar = inp.analysis_result or {}
        if ar.get("confidence") is not None:
            try:
                score = max(score, float(ar["confidence"]))
            except (TypeError, ValueError):
                pass

        if datasets:
            score += 0.15
        if any(d.source or d.source_url or d.provider for d in datasets):
            score += 0.1
        if tools:
            score += 0.15
        if inp.join_plan or (inp.analysis_result or {}).get("join_strategy"):
            score += 0.05
        if warnings:
            score -= min(0.25, 0.05 * len(warnings))
        if inp.errors:
            score -= 0.15
        return round(max(0.0, min(1.0, score)), 4)

    def _analysis_snippet(self, analysis_result: Optional[dict[str, Any]]) -> str:
        if not analysis_result:
            return ""
        for key in ("answer", "summary", "insight", "reasoning"):
            val = analysis_result.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:240]
        insights = analysis_result.get("insights")
        if isinstance(insights, list) and insights:
            first = insights[0]
            if isinstance(first, str):
                return first[:240]
            if isinstance(first, dict):
                return str(first.get("summary") or first.get("text") or first)[:240]
        return ""

    def _build_summary(
        self,
        inp: ExplanationInput,
        datasets: list[DatasetCitation],
        tools: list[ToolStepExplanation],
        snippet: str,
    ) -> str:
        if snippet and len(snippet) < 200:
            base = snippet
        else:
            base = "Analytical response generated from the configured data and tool pipeline."
        n_ds = len(datasets)
        n_tools = len(tools)
        extra = []
        if n_ds:
            extra.append(f"{n_ds} dataset(s)")
        if n_tools:
            extra.append(f"{n_tools} analytical tool(s)")
        if extra:
            base = f"{base} Used {', '.join(extra)}."
        return base

    @staticmethod
    def _citation_label(index: int, cit: DatasetCitation) -> str:
        parts = []
        if cit.source:
            parts.append(str(cit.source))
        elif cit.provider:
            parts.append(str(cit.provider))
        if cit.topic:
            parts.append(str(cit.topic))
        elif cit.dataset_id:
            parts.append(str(cit.dataset_id))
        body = " — ".join(parts) if parts else f"Dataset {index}"
        return f"[{index}] {body}"


class LLMExplainer(Explainer):
    """
    Placeholder / optional LLM-backed explainer.

    Falls back to RuleBasedExplainer when LLM is disabled or fails.
    Callers keep using generate_explanation() unchanged.
    """

    name = "llm"

    def __init__(self, fallback: Explainer | None = None):
        self._fallback = fallback or RuleBasedExplainer()

    def explain(self, explanation_input: ExplanationInput) -> ExplanationResult:
        # Always produce structured base from rules
        base = self._fallback.explain(explanation_input)

        try:
            from backend.config import settings

            use_llm = bool(
                getattr(settings, "USE_LLM_INTENT", False)
                or getattr(settings, "USE_LLM_PLANNER", False)
            )
        except Exception:
            use_llm = False

        if not use_llm:
            base.explainer = f"{self.name}+{base.explainer}"
            base.metadata["llm_used"] = False
            return base

        payload = {
            "question": explanation_input.question,
            "style": explanation_input.style.value
            if isinstance(explanation_input.style, ExplanationStyle)
            else str(explanation_input.style),
            "base_explanation": {
                "summary": base.summary,
                "reasoning_summary": base.reasoning_summary,
                "datasets": [d.to_dict() for d in base.datasets_used],
                "tools": [t.to_dict() for t in base.tools_executed],
                "filters": [f.to_dict() for f in base.filters_applied],
                "joins": base.joins_performed.to_dict() if base.joins_performed else None,
                "warnings": base.warnings,
                "limitations": base.limitations,
                "confidence": base.confidence,
            },
        }
        prompt = build_llm_explanation_prompt(payload)
        try:
            from backend.llm.ollama_client import invoke_llm

            raw = invoke_llm(prompt)
            parsed = _parse_llm_json(raw)
            if not parsed:
                raise ValueError("LLM returned empty explanation")

            if parsed.get("summary"):
                base.summary = str(parsed["summary"])
            if parsed.get("reasoning_summary"):
                base.reasoning_summary = str(parsed["reasoning_summary"])
            if parsed.get("short_text"):
                base.short_text = str(parsed["short_text"])
            if parsed.get("detailed_text"):
                base.detailed_text = str(parsed["detailed_text"])
            if parsed.get("technical_text"):
                base.technical_text = str(parsed["technical_text"])
            if isinstance(parsed.get("limitations"), list):
                base.limitations = [str(x) for x in parsed["limitations"]]
            if parsed.get("confidence") is not None:
                try:
                    base.confidence = max(0.0, min(1.0, float(parsed["confidence"])))
                except (TypeError, ValueError):
                    pass

            style = base.style
            base.explanation_text = {
                ExplanationStyle.SHORT: base.short_text,
                ExplanationStyle.DETAILED: base.detailed_text,
                ExplanationStyle.TECHNICAL: base.technical_text,
            }.get(style, base.detailed_text)
            base.explainer = self.name
            base.metadata["llm_used"] = True
            return base
        except Exception as exc:
            logger.warning(
                "LLM explanation failed; using rule-based",
                extra={"error": str(exc)},
            )
            base.warnings.append(f"LLM explanation failed: {exc}")
            base.explainer = f"{self.name}_fallback+{base.explainer}"
            base.metadata["llm_used"] = False
            return base


def _parse_llm_json(response: str) -> Optional[dict[str, Any]]:
    if not response:
        return None
    text = response.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_default_explainer: Explainer | None = None


def get_default_explainer() -> Explainer:
    global _default_explainer
    if _default_explainer is None:
        _default_explainer = RuleBasedExplainer()
    return _default_explainer


def set_default_explainer(explainer: Explainer) -> None:
    global _default_explainer
    _default_explainer = explainer


def reset_default_explainer() -> None:
    global _default_explainer
    _default_explainer = None


def generate_explanation(
    *,
    analysis_result: Any = None,
    execution_plan: Any = None,
    datasets_used: Any = None,
    join_plan: Any = None,
    question: str = "",
    style: Any = ExplanationStyle.DETAILED,
    **kwargs: Any,
) -> ExplanationResult:
    """
    Module-level entrypoint.

    Future LLMExplainer can replace the default without changing callers.
    """
    return get_default_explainer().generate_explanation(
        analysis_result=analysis_result,
        execution_plan=execution_plan,
        datasets_used=datasets_used,
        join_plan=join_plan,
        question=question,
        style=style,
        **kwargs,
    )
