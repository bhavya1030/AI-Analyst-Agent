"""Dataset Learning Service — update Registry after acquire + profile.

Does not download, profile, clean, analyze, or decide retrieval sources.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.core.logger import get_logger
from backend.learning.dedupe import find_duplicate, normalize_url
from backend.learning.embeddings import EmbeddingGenerator, NoOpEmbeddingGenerator
from backend.learning.exceptions import LearningRegistryError, LearningValidationError
from backend.learning.models import LearningAction, LearningInput, LearningResult, _utc_now_iso
from backend.registry import DatasetMetadata, DatasetRegistryService
from backend.registry.exceptions import DatasetNotFoundError, DatasetValidationError
from backend.registry.models import new_dataset_id

logger = get_logger(__name__)


class DatasetLearningService:
    """Learn from retrieval + acquisition + intelligence into Dataset Registry."""

    def __init__(
        self,
        registry: DatasetRegistryService | None = None,
        embedding_generator: EmbeddingGenerator | None = None,
    ):
        self._registry = registry or DatasetRegistryService()
        self._embeddings = embedding_generator or NoOpEmbeddingGenerator()

    def learn_dataset(
        self,
        *,
        retrieval: Any = None,
        acquisition: Any = None,
        profile: Any = None,
    ) -> LearningResult:
        """
        Accept RetrievalResult, AcquisitionResult, DatasetProfile (objects or dicts).

        Decides new / existing / updated, writes Registry only.
        """
        try:
            incoming = self._build_learning_input(retrieval, acquisition, profile)
        except LearningValidationError as exc:
            return LearningResult(
                action_taken=LearningAction.FAILED,
                reason=str(exc),
            )

        if not acquisition_ok(acquisition):
            return LearningResult(
                action_taken=LearningAction.SKIPPED,
                reason="Acquisition was not successful; nothing to learn.",
            )

        if not incoming.local_path and not incoming.download_url:
            return LearningResult(
                action_taken=LearningAction.FAILED,
                reason="Need local_path or download_url to register a dataset.",
            )

        try:
            existing = self._find_existing(incoming)
        except Exception as exc:
            return LearningResult(
                action_taken=LearningAction.FAILED,
                reason=f"Duplicate lookup failed: {exc}",
            )

        now = _utc_now_iso()

        if existing is None:
            return self._create(incoming, now)
        return self._update(existing, incoming, now)

    # ------------------------------------------------------------------
    # Create / update
    # ------------------------------------------------------------------

    def _create(self, incoming: LearningInput, now: str) -> LearningResult:
        meta = self._to_registry_metadata(incoming, existing=None, now=now, usage_count=1)
        meta.last_used = now
        try:
            saved = self._registry.insert_dataset(meta)
        except (DatasetValidationError, Exception) as exc:
            logger.warning("Learning insert failed", extra={"error": str(exc)})
            return LearningResult(
                action_taken=LearningAction.FAILED,
                reason=f"Registry insert failed: {exc}",
            )

        embedding_ref = self._maybe_embed(saved, incoming)
        if embedding_ref and embedding_ref != saved.embedding_ref:
            try:
                saved.embedding_ref = embedding_ref
                saved = self._registry.update_dataset(saved)
            except Exception as exc:
                logger.warning("Embedding ref update failed", extra={"error": str(exc)})

        logger.info(
            "Learning created registry entry",
            extra={"registry_id": saved.dataset_id, "topic": saved.topic},
        )
        return LearningResult(
            action_taken=LearningAction.CREATED,
            registry_id=saved.dataset_id,
            created=True,
            updated=False,
            duplicate_detected=False,
            reason="New dataset registered.",
            embedding_ref=saved.embedding_ref,
            metadata_snapshot=saved.to_dict(),
        )

    def _update(
        self,
        existing: DatasetMetadata,
        incoming: LearningInput,
        now: str,
    ) -> LearningResult:
        usage = int(existing.usage_count or 0) + 1
        meta = self._to_registry_metadata(
            incoming,
            existing=existing,
            now=now,
            usage_count=usage,
        )
        meta.dataset_id = existing.dataset_id
        meta.created_at = existing.created_at
        meta.last_used = now
        meta.last_updated = now

        # Preserve embedding_ref unless generator returns a new one later
        if not meta.embedding_ref:
            meta.embedding_ref = existing.embedding_ref

        try:
            saved = self._registry.update_dataset(meta)
        except (DatasetNotFoundError, DatasetValidationError, Exception) as exc:
            # Fallback: try increment + partial fields via update dict path
            try:
                self._registry.increment_usage(existing.dataset_id)
            except Exception:
                pass
            logger.warning("Learning update failed", extra={"error": str(exc)})
            return LearningResult(
                action_taken=LearningAction.FAILED,
                registry_id=existing.dataset_id,
                duplicate_detected=True,
                reason=f"Registry update failed: {exc}",
            )

        embedding_ref = self._maybe_embed(saved, incoming)
        if embedding_ref and embedding_ref != saved.embedding_ref:
            try:
                saved.embedding_ref = embedding_ref
                saved = self._registry.update_dataset(saved)
            except Exception as exc:
                logger.warning("Embedding ref update failed", extra={"error": str(exc)})

        logger.info(
            "Learning updated registry entry",
            extra={"registry_id": saved.dataset_id, "usage_count": saved.usage_count},
        )
        return LearningResult(
            action_taken=LearningAction.UPDATED,
            registry_id=saved.dataset_id,
            created=False,
            updated=True,
            duplicate_detected=True,
            reason="Existing dataset updated (duplicate identity matched).",
            embedding_ref=saved.embedding_ref,
            metadata_snapshot=saved.to_dict(),
        )

    # ------------------------------------------------------------------
    # Identity / merge
    # ------------------------------------------------------------------

    def _find_existing(self, incoming: LearningInput) -> Optional[DatasetMetadata]:
        candidates: list[DatasetMetadata] = []

        if incoming.dataset_id:
            by_id = self._registry.get_by_dataset_id(incoming.dataset_id)
            if by_id is not None:
                return by_id

        # Topic-scoped candidates + recent list for checksum/url scan
        if incoming.topic:
            candidates.extend(self._registry.get_by_topic(incoming.topic, limit=50) or [])
        candidates.extend(self._registry.list_datasets(limit=200) or [])

        # Dedupe candidate list by dataset_id
        by_id: dict[str, DatasetMetadata] = {}
        for c in candidates:
            if c and c.dataset_id:
                by_id[c.dataset_id] = c

        return find_duplicate(list(by_id.values()), incoming)

    def _to_registry_metadata(
        self,
        incoming: LearningInput,
        *,
        existing: Optional[DatasetMetadata],
        now: str,
        usage_count: int,
    ) -> DatasetMetadata:
        title = incoming.title or (existing.title if existing else "") or incoming.topic or "Untitled dataset"
        topic = incoming.topic or (existing.topic if existing else "") or "general"

        tags = list(incoming.tags or [])
        for kw in incoming.topic_keywords or []:
            if kw and kw not in tags:
                tags.append(kw)
        if incoming.domain and incoming.domain not in tags:
            tags.append(incoming.domain)
        for country in (incoming.countries_regions or [])[:10]:
            if country and country not in tags:
                tags.append(country)

        columns = list(incoming.columns or [])
        if not columns and existing:
            columns = list(existing.columns or [])

        summary = incoming.summary or ""
        profile_bits = []
        if incoming.dataset_type and incoming.dataset_type != "unknown":
            profile_bits.append(f"type={incoming.dataset_type}")
        if incoming.domain and incoming.domain != "general":
            profile_bits.append(f"domain={incoming.domain}")
        if incoming.time_column:
            profile_bits.append(f"time_column={incoming.time_column}")
        if incoming.entity_column:
            profile_bits.append(f"entity_column={incoming.entity_column}")
        if incoming.countries_regions:
            profile_bits.append(
                "countries=" + ",".join(str(c) for c in incoming.countries_regions[:8])
            )
        if profile_bits:
            profile_line = "Profile: " + "; ".join(profile_bits)
            summary = f"{summary}\n{profile_line}".strip() if summary else profile_line

        if existing and existing.summary and not incoming.summary:
            # Keep prior human description if we only added profile line
            if not summary.startswith("Profile:"):
                pass

        download_url = incoming.download_url or (existing.download_url if existing else None)
        local_path = incoming.local_path or (existing.local_path if existing else None)
        checksum = incoming.checksum or (existing.checksum if existing else None)
        file_format = incoming.file_format or (existing.file_format if existing else "unknown")
        source = incoming.source or (existing.source if existing else "")
        source_type = incoming.source_type or (existing.source_type if existing else "Other")
        description = incoming.description or (existing.description if existing else "")
        date_range = incoming.date_range if incoming.date_range is not None else (
            existing.date_range if existing else None
        )
        row_count = (
            incoming.row_count
            if incoming.row_count is not None
            else (existing.row_count if existing else None)
        )

        dataset_id = (
            existing.dataset_id
            if existing
            else (incoming.dataset_id or new_dataset_id())
        )

        return DatasetMetadata(
            dataset_id=dataset_id,
            title=title,
            topic=topic,
            description=description,
            source=source,
            source_type=source_type,
            download_url=download_url,
            local_path=local_path,
            file_format=file_format or "unknown",
            tags=tags,
            columns=columns,
            row_count=row_count,
            date_range=date_range,
            summary=summary,
            created_at=(existing.created_at if existing else now),
            last_used=now,
            last_updated=now,
            usage_count=usage_count,
            checksum=checksum,
            embedding_ref=incoming.embedding_ref or (existing.embedding_ref if existing else None),
            is_active=True,
        )

    def _maybe_embed(self, saved: DatasetMetadata, incoming: LearningInput) -> Optional[str]:
        """Future: generate embedding_ref after registry write."""
        try:
            profile_snapshot = {
                "domain": incoming.domain,
                "dataset_type": incoming.dataset_type,
                "topic_keywords": incoming.topic_keywords,
                "time_column": incoming.time_column,
                "entity_column": incoming.entity_column,
            }
            return self._embeddings.generate(saved, profile=profile_snapshot)
        except Exception as exc:
            logger.warning("Embedding generator failed", extra={"error": str(exc)})
            return None

    # ------------------------------------------------------------------
    # Input normalization
    # ------------------------------------------------------------------

    def _build_learning_input(
        self,
        retrieval: Any,
        acquisition: Any,
        profile: Any,
    ) -> LearningInput:
        r = _as_dict(retrieval)
        a = _as_dict(acquisition)
        p = _as_dict(profile)

        if not a and not r and not p:
            raise LearningValidationError(
                "At least one of retrieval, acquisition, or profile is required."
            )

        r_meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}

        topic = (
            r.get("topic")
            or r_meta.get("topic")
            or p.get("topic")
            or ""
        )
        title = (
            r_meta.get("title")
            or r.get("title")
            or topic
            or "Untitled dataset"
        )
        source = (
            r_meta.get("provider")
            or r_meta.get("source")
            or r.get("provider")
            or a.get("provider")
            or ""
        )
        source_type = r_meta.get("source_type") or _source_type_from_provider(
            r.get("provider") or a.get("provider") or r_meta.get("provider")
        )

        download_url = (
            r.get("download_url")
            or a.get("source_url")
            or r_meta.get("download_url")
            or r_meta.get("url")
        )
        local_path = (
            a.get("local_path")
            or r.get("local_path")
            or p.get("local_path")
            or r_meta.get("local_path")
        )
        dataset_id = (
            a.get("dataset_id")
            or r.get("dataset_id")
            or r_meta.get("dataset_id")
        )
        checksum = a.get("checksum")
        file_format = (
            a.get("detected_format")
            or p.get("file_format")
            or r_meta.get("file_format")
            or "unknown"
        )

        tags = list(r_meta.get("tags") or [])
        # Provenance tags for multi-provider retrieval
        for key, prefix in (
            ("provider", "provider:"),
            ("license", "license:"),
            ("dataset_version", "version:"),
        ):
            val = r_meta.get(key)
            if val:
                label = f"{prefix}{val}"
                if label not in tags and str(val) not in tags:
                    tags.append(label)
        columns = list(p.get("column_names") or r_meta.get("columns") or [])
        row_count = p.get("row_count")
        if row_count is None and a.get("dataset_size") is not None:
            # size is bytes, not rows — leave None
            pass
        date_range = p.get("date_range")
        description = r_meta.get("description") or ""
        summary = r_meta.get("summary") or ""
        # Persist download provenance in summary for operators / audit
        provenance_bits = []
        if r_meta.get("provider") or source:
            provenance_bits.append(f"provider={r_meta.get('provider') or source}")
        if r_meta.get("license"):
            provenance_bits.append(f"license={r_meta.get('license')}")
        if r_meta.get("dataset_version"):
            provenance_bits.append(f"version={r_meta.get('dataset_version')}")
        src_url = r_meta.get("source_url") or download_url
        if src_url:
            provenance_bits.append(f"source_url={src_url}")
        if r_meta.get("download_timestamp"):
            provenance_bits.append(f"downloaded_at={r_meta.get('download_timestamp')}")
        if provenance_bits:
            line = "Provenance: " + "; ".join(provenance_bits)
            summary = f"{summary}\n{line}".strip() if summary else line

        return LearningInput(
            dataset_id=dataset_id,
            title=str(title),
            topic=str(topic or "general"),
            description=str(description or ""),
            source=str(source or ""),
            source_type=str(source_type or "Other"),
            download_url=download_url,
            local_path=local_path,
            file_format=str(file_format or "unknown"),
            tags=tags,
            columns=[str(c) for c in columns],
            row_count=int(row_count) if row_count is not None else None,
            date_range=date_range if isinstance(date_range, dict) else None,
            summary=str(summary or ""),
            checksum=checksum,
            domain=str(p.get("domain") or "general"),
            time_column=p.get("time_column"),
            entity_column=p.get("entity_column"),
            countries_regions=list(p.get("countries_regions") or []),
            topic_keywords=list(p.get("topic_keywords") or []),
            dataset_type=str(p.get("dataset_type") or "unknown"),
        )


def acquisition_ok(acquisition: Any) -> bool:
    if acquisition is None:
        # Allow learn from registry-only path? Spec says after acquired+profiled.
        # If acquisition omitted entirely, skip.
        return False
    data = _as_dict(acquisition)
    if "success" in data:
        return bool(data.get("success"))
    # Object without success field — require local_path
    return bool(data.get("local_path"))


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "to_dict"):
        try:
            return dict(obj.to_dict())
        except Exception:
            pass
    # duck-type common fields
    keys = [
        "status", "dataset_id", "local_path", "download_url", "metadata", "provider",
        "topic", "reason", "success", "checksum", "detected_format", "dataset_size",
        "source_url", "errors", "dataset_type", "row_count", "column_names", "column_types",
        "time_column", "entity_column", "numeric_metrics", "categorical_fields",
        "date_range", "countries_regions", "topic_keywords", "domain", "file_format",
        "summary", "title", "source", "source_type", "tags", "columns",
    ]
    out = {}
    for k in keys:
        if hasattr(obj, k):
            val = getattr(obj, k)
            if hasattr(val, "value"):  # enum
                try:
                    val = val.value
                except Exception:
                    pass
            out[k] = val
    return out


def _source_type_from_provider(provider: str | None) -> str:
    p = (provider or "").lower()
    if "github" in p:
        return "GitHub"
    if "hugging" in p or "hf" in p:
        return "HuggingFace"
    if "world bank" in p or "world_bank" in p:
        return "API"
    if "oecd" in p or "imf" in p or "official" in p or "api" in p:
        return "API"
    if "wikipedia" in p or "web" in p or "internet" in p:
        return "Web"
    if "session" in p:
        return "Other"
    if "registry" in p:
        return "Other"
    return "Other"


# ---------------------------------------------------------------------------
# Module API
# ---------------------------------------------------------------------------


def learn_dataset(
    *,
    retrieval: Any = None,
    acquisition: Any = None,
    profile: Any = None,
    embedding_generator: EmbeddingGenerator | None = None,
) -> LearningResult:
    service = DatasetLearningService(embedding_generator=embedding_generator)
    return service.learn_dataset(
        retrieval=retrieval,
        acquisition=acquisition,
        profile=profile,
    )
