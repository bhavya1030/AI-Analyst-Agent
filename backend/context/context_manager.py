"""Conversation Context Manager — public API for multi-turn memory.

Exposes:
  save_context / load_context / update_context / resolve_reference / clear_context

Does NOT modify Planner. Does NOT store DataFrames.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Optional, Sequence

from backend.context.conversation_memory import (
    DEFAULT_TTL_SECONDS,
    ConversationMemoryStore,
    get_default_store,
)
from backend.context.exceptions import (
    ContextNotFoundError,
    ContextValidationError,
)
from backend.context.models import (
    AnalysisStep,
    ConversationContext,
    DatasetRef,
    FilterSpec,
    ResolvedRequest,
    VisualizationRef,
    _utc_now_iso,
)
from backend.context.reference_resolver import ReferenceResolver
from backend.core.logger import get_logger

logger = get_logger(__name__)

# Cap history growth
_MAX_ANALYSIS_STEPS = 50
_MAX_VISUALIZATIONS = 20
_MAX_DATASETS = 10


class ConversationContextManager:
    """
    Manage per-conversation context for follow-up resolution.

    Multiple conversations are supported simultaneously via conversation_id.
    Context expires after ``ttl_seconds`` of inactivity (configurable).
    """

    def __init__(
        self,
        *,
        store: ConversationMemoryStore | None = None,
        resolver: ReferenceResolver | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        self._store = store or get_default_store(ttl_seconds=ttl_seconds)
        if ttl_seconds and ttl_seconds != self._store.ttl_seconds:
            self._store.set_ttl(ttl_seconds)
        self._resolver = resolver or ReferenceResolver()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API (required)
    # ------------------------------------------------------------------

    def save_context(
        self,
        conversation_id: str,
        context: ConversationContext | dict[str, Any],
    ) -> ConversationContext:
        """
        Persist full context for a conversation (overwrite).

        Accepts ConversationContext or dict. Strips any accidental DataFrame-like keys.
        """
        cid = self._require_id(conversation_id)
        ctx = self._coerce_context(context, conversation_id=cid)
        ctx.conversation_id = cid
        self._sanitize(ctx)
        saved = self._store.put(ctx)
        logger.info("Context saved", extra={"conversation_id": cid})
        return saved

    def load_context(
        self,
        conversation_id: str,
        *,
        touch: bool = True,
        create_if_missing: bool = False,
    ) -> ConversationContext:
        """
        Load context for conversation_id.

        Raises ContextNotFoundError / ContextExpiredError unless create_if_missing.
        """
        cid = self._require_id(conversation_id)
        try:
            ctx = self._store.get(cid, touch=touch, raise_if_missing=True, raise_if_expired=True)
            assert ctx is not None
            return ctx
        except ContextNotFoundError:
            if create_if_missing:
                empty = ConversationContext(conversation_id=cid)
                return self._store.put(empty)
            raise

    def update_context(
        self,
        conversation_id: str,
        *,
        # Dataset refs (no DataFrames)
        dataset: DatasetRef | dict[str, Any] | None = None,
        datasets: Sequence[DatasetRef | dict[str, Any]] | None = None,
        replace_datasets: bool = False,
        # Filters / entities
        filters: Sequence[FilterSpec | dict[str, Any]] | None = None,
        append_filters: bool = True,
        clear_filters: bool = False,
        countries: Sequence[str] | None = None,
        append_countries: bool = True,
        metrics: Sequence[str] | None = None,
        append_metrics: bool = True,
        # Viz / analysis
        visualization: VisualizationRef | dict[str, Any] | None = None,
        analysis_step: AnalysisStep | dict[str, Any] | None = None,
        # Conversation markers
        question: str | None = None,
        resolved_question: str | None = None,
        intent: str | None = None,
        operation: str | None = None,
        forecast_target: str | None = None,
        last_columns: Sequence[str] | None = None,
        entities: Sequence[str] | None = None,
        notes: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
        # Raw partial dict merge (shallow, sanitized)
        patch: dict[str, Any] | None = None,
    ) -> ConversationContext:
        """
        Merge updates into existing context (creates empty if missing).

        Never accepts or stores DataFrames.
        """
        cid = self._require_id(conversation_id)
        with self._lock:
            try:
                ctx = self._store.get(cid, touch=False, raise_if_missing=True)
            except ContextNotFoundError:
                ctx = ConversationContext(conversation_id=cid)
            assert ctx is not None

            if patch:
                ctx = self._apply_patch(ctx, patch)

            if clear_filters:
                ctx.filters = []

            if dataset is not None:
                ref = self._as_dataset_ref(dataset)
                ctx.active_datasets = self._upsert_dataset(ctx.active_datasets, ref)

            if datasets is not None:
                refs = [self._as_dataset_ref(d) for d in datasets]
                if replace_datasets:
                    ctx.active_datasets = refs[:_MAX_DATASETS]
                else:
                    for ref in refs:
                        ctx.active_datasets = self._upsert_dataset(ctx.active_datasets, ref)

            if filters is not None:
                parsed = [self._as_filter(f) for f in filters]
                if append_filters:
                    ctx.filters = (ctx.filters + parsed)[-20:]
                else:
                    ctx.filters = parsed[:20]

            if countries is not None:
                cleaned = [c.strip() for c in countries if c and str(c).strip()]
                if append_countries:
                    merged = list(ctx.selected_countries)
                    for c in cleaned:
                        if c not in merged:
                            merged.append(c)
                    ctx.selected_countries = merged[-30:]
                else:
                    ctx.selected_countries = cleaned[:30]

            if metrics is not None:
                cleaned_m = [m.strip() for m in metrics if m and str(m).strip()]
                if append_metrics:
                    merged_m = list(ctx.metrics)
                    for m in cleaned_m:
                        if m not in merged_m:
                            merged_m.append(m)
                    ctx.metrics = merged_m[-30:]
                else:
                    ctx.metrics = cleaned_m[:30]

            if visualization is not None:
                viz = self._as_viz(visualization)
                ctx.visualizations = (ctx.visualizations + [viz])[-_MAX_VISUALIZATIONS:]

            if analysis_step is not None:
                step = self._as_step(analysis_step)
                ctx.analysis_steps = (ctx.analysis_steps + [step])[-_MAX_ANALYSIS_STEPS:]

            if question is not None:
                ctx.last_question = str(question)
            if resolved_question is not None:
                ctx.last_resolved_question = str(resolved_question)
            if intent is not None:
                ctx.last_intent = str(intent)
            if operation is not None:
                ctx.last_operation = str(operation)
            if forecast_target is not None:
                ctx.last_forecast_target = str(forecast_target)
            if last_columns is not None:
                ctx.last_columns = [str(c) for c in last_columns][:50]
            if entities is not None:
                for e in entities:
                    e = str(e).strip()
                    if e and e not in ctx.entities:
                        ctx.entities.append(e)
                ctx.entities = ctx.entities[-50:]
            if notes is not None:
                ctx.notes.extend(str(n) for n in notes if n)
                ctx.notes = ctx.notes[-50:]
            if metadata:
                ctx.metadata.update(self._strip_heavy(metadata))

            self._sanitize(ctx)
            return self._store.put(ctx)

    def resolve_reference(
        self,
        conversation_id: str,
        question: str,
        *,
        allow_missing_context: bool = True,
    ) -> ResolvedRequest:
        """
        Resolve follow-up references in ``question`` against stored context.

        Returns ResolvedRequest for future Planner consumption.
        """
        cid = self._require_id(conversation_id)
        ctx: ConversationContext | None
        try:
            ctx = self._store.get(cid, touch=True, raise_if_missing=True, raise_if_expired=True)
        except ContextNotFoundError:
            if not allow_missing_context:
                raise
            ctx = None

        resolved = self._resolver.resolve(question, ctx, conversation_id=cid)
        logger.info(
            "Reference resolved",
            extra={
                "conversation_id": cid,
                "is_follow_up": resolved.is_follow_up,
                "n_refs": len(resolved.resolved_references),
            },
        )
        return resolved

    def clear_context(self, conversation_id: str) -> bool:
        """Remove context for conversation_id. Returns True if it existed."""
        cid = self._require_id(conversation_id)
        removed = self._store.delete(cid)
        logger.info(
            "Context cleared",
            extra={"conversation_id": cid, "existed": removed},
        )
        return removed

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def list_conversations(self) -> list[str]:
        return self._store.list_ids()

    def has_context(self, conversation_id: str) -> bool:
        return self._store.exists(conversation_id)

    def touch(self, conversation_id: str) -> ConversationContext:
        """Refresh activity timestamp without other changes."""
        return self.load_context(conversation_id, touch=True)

    def record_analysis(
        self,
        conversation_id: str,
        *,
        question: str,
        resolved_question: str = "",
        operation: str = "analyze",
        intent: str | None = None,
        summary: str = "",
        metrics: Sequence[str] | None = None,
        countries: Sequence[str] | None = None,
        dataset_topics: Sequence[str] | None = None,
    ) -> ConversationContext:
        step = AnalysisStep(
            operation=operation,
            intent=intent,
            question=question,
            resolved_question=resolved_question or question,
            summary=summary,
            metrics=list(metrics or []),
            countries=list(countries or []),
            dataset_topics=list(dataset_topics or []),
        )
        return self.update_context(
            conversation_id,
            analysis_step=step,
            question=question,
            resolved_question=resolved_question or question,
            intent=intent,
            operation=operation,
            metrics=metrics,
            countries=countries,
            append_metrics=True,
            append_countries=True,
        )

    def record_dataset(
        self,
        conversation_id: str,
        *,
        topic: str,
        local_path: str | None = None,
        dataset_id: str | None = None,
        download_url: str | None = None,
        source: str | None = None,
        columns: Sequence[str] | None = None,
        row_count: int | None = None,
        registry_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        set_active: bool = True,
    ) -> ConversationContext:
        ref = DatasetRef(
            dataset_id=dataset_id,
            local_path=local_path,
            download_url=download_url,
            topic=topic,
            source=source,
            columns=list(columns or []),
            row_count=row_count,
            registry_id=registry_id,
            is_active=set_active,
            metadata=dict(metadata or {}),
        )
        return self.update_context(conversation_id, dataset=ref)

    def record_filter(
        self,
        conversation_id: str,
        *,
        column: str,
        operator: str,
        value: Any = None,
        value_to: Any = None,
        label: str = "",
    ) -> ConversationContext:
        if not label:
            label = f"{column} {operator} {value}"
            if value_to is not None:
                label = f"{column} {operator} {value}..{value_to}"
        return self.update_context(
            conversation_id,
            filters=[
                FilterSpec(
                    column=column,
                    operator=operator,
                    value=value,
                    value_to=value_to,
                    label=label,
                )
            ],
            append_filters=True,
        )

    def record_visualization(
        self,
        conversation_id: str,
        *,
        chart_type: str | None = None,
        columns: Sequence[str] | None = None,
        title: str | None = None,
        chart_id: str | None = None,
        artifact_ref: str | None = None,
    ) -> ConversationContext:
        return self.update_context(
            conversation_id,
            visualization=VisualizationRef(
                chart_type=chart_type,
                columns=list(columns or []),
                title=title,
                chart_id=chart_id,
                artifact_ref=artifact_ref,
            ),
            last_columns=list(columns or []) if columns else None,
            operation="visualization",
        )

    def set_ttl(self, ttl_seconds: int) -> None:
        self._store.set_ttl(ttl_seconds)

    def purge_expired(self) -> int:
        return self._store.purge_expired()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _require_id(conversation_id: str) -> str:
        cid = (conversation_id or "").strip()
        if not cid:
            raise ContextValidationError("conversation_id is required")
        return cid

    def _coerce_context(
        self,
        context: ConversationContext | dict[str, Any],
        *,
        conversation_id: str,
    ) -> ConversationContext:
        if isinstance(context, ConversationContext):
            ctx = context
        elif isinstance(context, dict):
            data = dict(context)
            data["conversation_id"] = data.get("conversation_id") or conversation_id
            # Strip heavy keys if present
            data = self._strip_heavy(data)
            # Remove any dataframe-looking keys
            for banned in ("data", "dataframe", "df", "merged_dataframe", "last_dataset"):
                data.pop(banned, None)
            if "active_datasets" in data or "conversation_id" in data:
                ctx = ConversationContext.from_dict(data)
            else:
                # Treat as patch-style dict → empty + patch
                ctx = ConversationContext(conversation_id=conversation_id)
                ctx = self._apply_patch(ctx, data)
        else:
            raise ContextValidationError("context must be ConversationContext or dict")
        return ctx

    def _apply_patch(
        self, ctx: ConversationContext, patch: dict[str, Any]
    ) -> ConversationContext:
        patch = self._strip_heavy(patch)
        mapping = {
            "last_question": "last_question",
            "last_resolved_question": "last_resolved_question",
            "last_intent": "last_intent",
            "last_operation": "last_operation",
            "last_forecast_target": "last_forecast_target",
        }
        for src, attr in mapping.items():
            if src in patch and patch[src] is not None:
                setattr(ctx, attr, patch[src])
        if "selected_countries" in patch and patch["selected_countries"] is not None:
            ctx.selected_countries = list(patch["selected_countries"])
        if "metrics" in patch and patch["metrics"] is not None:
            ctx.metrics = list(patch["metrics"])
        if "last_columns" in patch and patch["last_columns"] is not None:
            ctx.last_columns = list(patch["last_columns"])
        if "entities" in patch and patch["entities"] is not None:
            ctx.entities = list(patch["entities"])
        if "notes" in patch and patch["notes"] is not None:
            ctx.notes = list(patch["notes"])
        if "metadata" in patch and isinstance(patch["metadata"], dict):
            ctx.metadata.update(self._strip_heavy(patch["metadata"]))
        if "filters" in patch and patch["filters"] is not None:
            ctx.filters = [self._as_filter(f) for f in patch["filters"]]
        if "active_datasets" in patch and patch["active_datasets"] is not None:
            ctx.active_datasets = [self._as_dataset_ref(d) for d in patch["active_datasets"]]
        if "visualizations" in patch and patch["visualizations"] is not None:
            ctx.visualizations = [self._as_viz(v) for v in patch["visualizations"]]
        if "analysis_steps" in patch and patch["analysis_steps"] is not None:
            ctx.analysis_steps = [self._as_step(a) for a in patch["analysis_steps"]]
        return ctx

    @staticmethod
    def _strip_heavy(data: dict[str, Any]) -> dict[str, Any]:
        """Remove keys that look like DataFrames or huge chart JSON blobs."""
        banned = {
            "data",
            "dataframe",
            "df",
            "merged_dataframe",
            "last_dataset",
            "frame",
            "frames",
        }
        out: dict[str, Any] = {}
        for k, v in data.items():
            if k in banned:
                continue
            # Drop pandas-looking objects by type name
            type_name = type(v).__name__
            if type_name in {"DataFrame", "Series"}:
                continue
            # Drop huge chart dicts if nested under 'chart' with plotly shape
            if k in {"chart", "charts", "figure"} and isinstance(v, (dict, list)):
                # Keep only lightweight fingerprint if possible
                continue
            out[k] = v
        return out

    @staticmethod
    def _as_dataset_ref(value: DatasetRef | dict[str, Any]) -> DatasetRef:
        if isinstance(value, DatasetRef):
            return value
        if isinstance(value, dict):
            clean = {
                k: v
                for k, v in value.items()
                if k not in {"data", "dataframe", "df"}
                and type(v).__name__ not in {"DataFrame", "Series"}
            }
            return DatasetRef.from_dict(clean)
        raise ContextValidationError("dataset must be DatasetRef or dict")

    @staticmethod
    def _as_filter(value: FilterSpec | dict[str, Any]) -> FilterSpec:
        if isinstance(value, FilterSpec):
            return value
        if isinstance(value, dict):
            return FilterSpec.from_dict(value)
        raise ContextValidationError("filter must be FilterSpec or dict")

    @staticmethod
    def _as_viz(value: VisualizationRef | dict[str, Any]) -> VisualizationRef:
        if isinstance(value, VisualizationRef):
            return value
        if isinstance(value, dict):
            # Never keep full plotly data
            clean = {
                k: v
                for k, v in value.items()
                if k
                in {
                    "chart_type",
                    "columns",
                    "title",
                    "chart_id",
                    "artifact_ref",
                    "created_at",
                }
            }
            return VisualizationRef.from_dict(clean)
        raise ContextValidationError("visualization must be VisualizationRef or dict")

    @staticmethod
    def _as_step(value: AnalysisStep | dict[str, Any]) -> AnalysisStep:
        if isinstance(value, AnalysisStep):
            return value
        if isinstance(value, dict):
            return AnalysisStep.from_dict(value)
        raise ContextValidationError("analysis_step must be AnalysisStep or dict")

    @staticmethod
    def _upsert_dataset(
        existing: list[DatasetRef], ref: DatasetRef
    ) -> list[DatasetRef]:
        # Mark others inactive if new is active
        out: list[DatasetRef] = []
        replaced = False
        for d in existing:
            same = False
            if ref.dataset_id and d.dataset_id and d.dataset_id == ref.dataset_id:
                same = True
            elif ref.local_path and d.local_path and d.local_path == ref.local_path:
                same = True
            elif ref.topic and d.topic and d.topic.lower() == ref.topic.lower():
                same = True
            if same:
                if ref.is_active:
                    d.is_active = False
                out.append(ref)
                replaced = True
            else:
                if ref.is_active:
                    d.is_active = False
                out.append(d)
        if not replaced:
            if ref.is_active:
                for d in out:
                    d.is_active = False
            out.append(ref)
        return out[-_MAX_DATASETS:]

    @staticmethod
    def _sanitize(ctx: ConversationContext) -> None:
        """Ensure no DataFrame sneaks into metadata/notes structure."""
        ctx.metadata = {
            k: v
            for k, v in (ctx.metadata or {}).items()
            if type(v).__name__ not in {"DataFrame", "Series"}
        }
        for d in ctx.active_datasets:
            d.metadata = {
                k: v
                for k, v in (d.metadata or {}).items()
                if type(v).__name__ not in {"DataFrame", "Series"}
            }


# ---------------------------------------------------------------------------
# Module-level façade (process default manager)
# ---------------------------------------------------------------------------

_default_manager: ConversationContextManager | None = None
_manager_lock = threading.Lock()


def get_context_manager(ttl_seconds: int | None = None) -> ConversationContextManager:
    global _default_manager
    with _manager_lock:
        if _default_manager is None:
            _default_manager = ConversationContextManager(
                ttl_seconds=ttl_seconds or DEFAULT_TTL_SECONDS
            )
        elif ttl_seconds is not None:
            _default_manager.set_ttl(ttl_seconds)
        return _default_manager


def reset_context_manager() -> None:
    """Test helper."""
    global _default_manager
    from backend.context.conversation_memory import reset_default_store

    with _manager_lock:
        _default_manager = None
        reset_default_store()


def save_context(
    conversation_id: str, context: ConversationContext | dict[str, Any]
) -> ConversationContext:
    return get_context_manager().save_context(conversation_id, context)


def load_context(
    conversation_id: str, **kwargs: Any
) -> ConversationContext:
    return get_context_manager().load_context(conversation_id, **kwargs)


def update_context(conversation_id: str, **kwargs: Any) -> ConversationContext:
    return get_context_manager().update_context(conversation_id, **kwargs)


def resolve_reference(
    conversation_id: str, question: str, **kwargs: Any
) -> ResolvedRequest:
    return get_context_manager().resolve_reference(conversation_id, question, **kwargs)


def clear_context(conversation_id: str) -> bool:
    return get_context_manager().clear_context(conversation_id)
