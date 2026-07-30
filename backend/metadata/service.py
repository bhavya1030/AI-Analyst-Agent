"""Metadata generation service: generate → register → apply to graph/session state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backend.core.logger import get_logger
from backend.metadata.generator import generate_metadata
from backend.metadata.models import GeneratedDatasetMetadata, is_placeholder_label
from backend.metadata.topic_detection import prefer_non_placeholder

logger = get_logger(__name__)


class DatasetMetadataService:
    """High-level API for auto metadata + registry population."""

    def generate(
        self,
        *,
        df: pd.DataFrame | None = None,
        local_path: str | Path | None = None,
        columns: list[str] | None = None,
        question: str | None = None,
        hint_topic: str | None = None,
        source: str = "",
        source_type: str = "Other",
        download_url: str | None = None,
        use_llm: bool | None = None,
        profile: dict[str, Any] | None = None,
    ) -> GeneratedDatasetMetadata:
        if use_llm is None:
            try:
                from backend.config import settings

                use_llm = bool(getattr(settings, "USE_LLM_METADATA", False))
            except Exception:
                use_llm = False

        return generate_metadata(
            df=df,
            local_path=local_path,
            columns=columns,
            question=question,
            hint_topic=hint_topic,
            source=source,
            source_type=source_type,
            download_url=download_url,
            use_llm=bool(use_llm),
            profile=profile,
        )

    def register(
        self,
        meta: GeneratedDatasetMetadata,
        *,
        profile: dict[str, Any] | None = None,
    ) -> GeneratedDatasetMetadata:
        """Upsert into Dataset Registry; attach dataset_id on success."""
        try:
            from backend.learning import learn_dataset
        except Exception as exc:
            logger.warning("Learning unavailable; skip registry write", extra={"error": str(exc)})
            return meta

        retrieval = {
            "topic": meta.topic or meta.title,
            "title": meta.title,
            "download_url": meta.download_url,
            "local_path": meta.local_path,
            "dataset_id": meta.dataset_id,
            "metadata": {
                "title": meta.title,
                "topic": meta.topic or meta.title,
                "description": meta.description,
                "source": meta.source,
                "source_type": meta.source_type,
                "download_url": meta.download_url,
                "local_path": meta.local_path,
                "file_format": meta.file_format,
                "tags": meta.tags,
                "keywords": meta.keywords,
                "columns": meta.columns,
                "domain": meta.domain,
                "country": meta.country,
                "metrics": meta.metrics,
                "summary": meta.summary,
                "time_column": meta.time_column,
                "entity_column": meta.primary_entity,
                "primary_entity": meta.primary_entity,
            },
            "provider": meta.source or meta.source_type,
        }
        acquisition = {
            "success": True,
            "local_path": meta.local_path,
            "source_url": meta.download_url,
            "checksum": meta.checksum,
            "detected_format": meta.file_format,
            "dataset_id": meta.dataset_id,
        }
        profile_payload = dict(profile or {})
        profile_payload.setdefault("column_names", meta.columns)
        profile_payload.setdefault("row_count", meta.row_count)
        profile_payload.setdefault("domain", meta.domain)
        profile_payload.setdefault("time_column", meta.time_column)
        profile_payload.setdefault("entity_column", meta.primary_entity)
        profile_payload.setdefault("countries_regions", meta.country)
        profile_payload.setdefault("topic_keywords", meta.keywords)
        profile_payload.setdefault("numeric_metrics", meta.metrics)
        profile_payload.setdefault("date_range", meta.date_range)
        profile_payload.setdefault("file_format", meta.file_format)
        profile_payload.setdefault("dataset_type", meta.dataset_type)
        profile_payload.setdefault("local_path", meta.local_path)

        try:
            result = learn_dataset(
                retrieval=retrieval,
                acquisition=acquisition,
                profile=profile_payload,
            )
            result_dict = result.to_dict() if hasattr(result, "to_dict") else dict(result)
            registry_id = result_dict.get("registry_id")
            if registry_id:
                meta.dataset_id = str(registry_id)
            snap = result_dict.get("metadata_snapshot") or {}
            if snap.get("title") and not is_placeholder_label(snap.get("title")):
                # Prefer registry title if learning refined it
                pass
            logger.info(
                "Metadata registered in dataset registry",
                extra={
                    "registry_id": meta.dataset_id,
                    "title": meta.title,
                    "action": result_dict.get("action_taken"),
                },
            )
        except Exception as exc:
            logger.warning("Registry population failed", extra={"error": str(exc)})
            meta.notes.append(f"registry_error:{exc}")
        return meta

    def apply_to_state(self, state: dict[str, Any], meta: GeneratedDatasetMetadata) -> dict[str, Any]:
        """Write generated metadata into LangGraph / session-facing state."""
        title = prefer_non_placeholder(meta.title, meta.topic)
        topic = prefer_non_placeholder(meta.topic, meta.title)

        current_topic = state.get("dataset_topic")
        if is_placeholder_label(current_topic) or not current_topic:
            state["dataset_topic"] = topic
        elif is_placeholder_label(state.get("dataset_topic")):
            state["dataset_topic"] = topic

        state["dataset_name"] = title
        state["dataset_title"] = title
        if meta.dataset_id:
            state["dataset_id"] = meta.dataset_id
            state["registry_id"] = meta.dataset_id

        existing = dict(state.get("dataset_metadata") or {})
        existing.update(
            {
                "title": title,
                "topic": topic,
                "description": meta.description,
                "domain": meta.domain,
                "country": meta.country,
                "metrics": meta.metrics,
                "time_column": meta.time_column,
                "primary_entity": meta.primary_entity,
                "entity_column": meta.primary_entity,
                "tags": meta.tags,
                "keywords": meta.keywords,
                "summary": meta.summary,
                "columns": meta.columns or existing.get("columns"),
                "row_count": meta.row_count if meta.row_count is not None else existing.get("row_count"),
                "date_range": meta.date_range or existing.get("date_range"),
                "source": meta.source or existing.get("source"),
                "source_type": meta.source_type or existing.get("source_type"),
                "local_path": meta.local_path or existing.get("local_path"),
                "download_url": meta.download_url or existing.get("download_url"),
                "dataset_id": meta.dataset_id or existing.get("dataset_id"),
                "file_format": meta.file_format,
                "dataset_type": meta.dataset_type,
            }
        )
        state["dataset_metadata"] = existing
        state["generated_metadata"] = meta.to_dict()

        # Focus helpers for downstream agents
        if meta.country and not state.get("focus_country"):
            state["focus_country"] = meta.country[0]
        if meta.metrics and not state.get("focus_metric"):
            # Prefer first human-friendly metric label
            state["focus_metric"] = str(meta.metrics[0])

        return state

    def generate_register_apply(
        self,
        state: dict[str, Any],
        *,
        df: pd.DataFrame | None = None,
        local_path: str | Path | None = None,
        register: bool = True,
        use_llm: bool | None = None,
    ) -> GeneratedDatasetMetadata:
        """One-shot: generate metadata, optionally register, apply to state."""
        path = local_path or state.get("local_path") or state.get("file_path")
        download_url = state.get("dataset_url")
        if download_url and str(download_url).startswith(("http://", "https://")):
            pass
        else:
            download_url = None

        source = state.get("source") or "user_upload"
        source_type = "Upload"
        if source in {"direct_url", "user_url"}:
            source_type = "UserURL"
        elif "registry" in str(source).lower():
            source_type = "Other"
        elif source not in {"user_upload", "upload"}:
            source_type = str(state.get("source_type") or "Other")

        profile = state.get("dataset_intelligence") or state.get("dataset_profile")
        if isinstance(profile, dict):
            profile_dict = profile
        else:
            profile_dict = None

        meta = self.generate(
            df=df if df is not None else state.get("data"),
            local_path=path if path and not str(path).startswith(("http://", "https://")) else None,
            columns=state.get("columns"),
            question=state.get("question"),
            hint_topic=state.get("dataset_topic"),
            source=str(source),
            source_type=source_type,
            download_url=download_url or state.get("dataset_url"),
            use_llm=use_llm,
            profile=profile_dict,
        )
        if register:
            meta = self.register(meta, profile=profile_dict)
        self.apply_to_state(state, meta)
        return meta


_default_service: DatasetMetadataService | None = None


def get_metadata_service() -> DatasetMetadataService:
    global _default_service
    if _default_service is None:
        _default_service = DatasetMetadataService()
    return _default_service


def generate_and_register_dataset_metadata(
    state: dict[str, Any],
    *,
    df: pd.DataFrame | None = None,
    local_path: str | Path | None = None,
    register: bool = True,
    use_llm: bool | None = None,
) -> GeneratedDatasetMetadata:
    """Module entrypoint used by agents."""
    return get_metadata_service().generate_register_apply(
        state,
        df=df,
        local_path=local_path,
        register=register,
        use_llm=use_llm,
    )
