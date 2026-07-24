"""Multi-Dataset Execution Engine.

Orchestrates:
  DatasetRequest[] → retrieve → acquire (if needed) → profile → learn
  → load DataFrames → schema alignment → merge → ExecutionResult

Reuses existing Retrieval, Acquisition, Intelligence, and Learning modules.
Does NOT redesign Planner, Data Engineer, EDA, or Visualization.
Does NOT compute statistics or generate charts.

API is stable for future parallel execution (asyncio / LangGraph branches)
via process_one() + map pattern without changing execute() signature.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import pandas as pd

from backend.core.logger import get_logger
from backend.execution.dataset_merger import DatasetMerger
from backend.execution.exceptions import ExecutionValidationError
from backend.execution.models import (
    DatasetExecStatus,
    ExecutionResult,
    JoinStrategy,
    ProcessedDataset,
)
from backend.execution.schema_alignment import SchemaAlignmentService
from backend.retrieval.models import DatasetRequest, NextAction, RetrievalResult, RetrievalStatus

logger = get_logger(__name__)

# Soft limits
MIN_DATASETS = 1
MAX_DATASETS = 10


class ExecutionEngine:
    """
    Execute multiple DatasetRequests end-to-end into a unified DataFrame.

    Dependencies are injectable for tests; defaults wire production services.
    """

    def __init__(
        self,
        *,
        retrieve_fn: Optional[Callable[[DatasetRequest], Any]] = None,
        acquire_fn: Optional[Callable[[Any], Any]] = None,
        profile_fn: Optional[Callable[[str], Any]] = None,
        learn_fn: Optional[Callable[..., Any]] = None,
        load_fn: Optional[Callable[[str], pd.DataFrame]] = None,
        schema_aligner: Optional[SchemaAlignmentService] = None,
        merger: Optional[DatasetMerger] = None,
    ):
        self._retrieve = retrieve_fn
        self._acquire = acquire_fn
        self._profile = profile_fn
        self._learn = learn_fn
        self._load = load_fn
        self._aligner = schema_aligner or SchemaAlignmentService()
        self._merger = merger or DatasetMerger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        requests: Sequence[DatasetRequest | dict[str, Any]],
        *,
        join_strategy: JoinStrategy | str = JoinStrategy.AUTO,
        required_topics: Optional[Sequence[str]] = None,
        optional_topics: Optional[Sequence[str]] = None,
    ) -> ExecutionResult:
        """
        Run multi-dataset pipeline for 1–10 DatasetRequests.

        Parameters
        ----------
        requests:
            Planner-produced DatasetRequest list.
        join_strategy:
            auto | inner | left | outer | concat (planner may set later).
        required_topics:
            Topics that must succeed; if omitted, all are optional but
            at least one success is required for overall success.
        optional_topics:
            Explicitly optional topics (default: all except required).
        """
        started = time.perf_counter()
        warnings: list[str] = []
        errors: list[str] = []

        try:
            normalized = self._normalize_requests(requests)
        except ExecutionValidationError as exc:
            return ExecutionResult(
                success=False,
                errors=[str(exc)],
                execution_time=time.perf_counter() - started,
            )

        topics = [r.normalized_topic() for r in normalized]
        required = set(t.strip() for t in (required_topics or []) if t)
        optional = set(t.strip() for t in (optional_topics or []) if t)
        # Default: all optional unless listed in required
        for t in topics:
            if t not in required:
                optional.add(t)

        # 1) Per-request pipeline (sequential today; process_one enables parallel later)
        processed: list[ProcessedDataset] = []
        for req in normalized:
            topic = req.normalized_topic()
            is_optional = topic not in required
            item = self.process_one(req, optional=is_optional)
            processed.append(item)
            if item.status == DatasetExecStatus.FAILED:
                msg = item.error or f"Dataset pipeline failed for '{topic}'"
                if is_optional:
                    warnings.append(msg)
                else:
                    errors.append(msg)
            elif item.warnings:
                warnings.extend(item.warnings)

        succeeded = [
            p
            for p in processed
            if p.status in (DatasetExecStatus.SUCCESS, DatasetExecStatus.PARTIAL)
            and p.local_path
        ]
        failed = [p for p in processed if p.status == DatasetExecStatus.FAILED]
        local_paths = [p.local_path for p in succeeded if p.local_path]

        if not succeeded:
            elapsed = time.perf_counter() - started
            if not errors:
                errors.append("No datasets were successfully prepared.")
            return ExecutionResult(
                success=False,
                datasets_processed=processed,
                local_paths=[],
                merged_dataframe=None,
                join_strategy=self._as_strategy(join_strategy),
                warnings=warnings,
                errors=errors,
                execution_time=elapsed,
                topics_requested=topics,
                topics_succeeded=[],
                topics_failed=[p.topic for p in failed],
            )

        # 2) Load DataFrames
        frames: list[pd.DataFrame] = []
        frame_topics: list[str] = []
        frame_profiles: list[Optional[dict]] = []
        loadable: list[ProcessedDataset] = []

        for p in succeeded:
            try:
                df = self._load_dataframe(p.local_path)  # type: ignore[arg-type]
                if df is None or df.empty:
                    warnings.append(f"Loaded empty DataFrame for '{p.topic}'; skipping.")
                    p.warnings.append("Empty DataFrame after load.")
                    continue
                frames.append(df)
                frame_topics.append(p.topic)
                frame_profiles.append(p.profile)
                loadable.append(p)
                p.row_count = int(len(df))
                p.columns = [str(c) for c in df.columns]
            except Exception as exc:
                msg = f"Failed to load '{p.topic}' from {p.local_path}: {exc}"
                logger.warning(msg)
                p.status = DatasetExecStatus.FAILED
                p.error = msg
                if p.optional:
                    warnings.append(msg)
                else:
                    errors.append(msg)

        if not frames:
            elapsed = time.perf_counter() - started
            errors.append("All prepared datasets failed to load into DataFrames.")
            return ExecutionResult(
                success=False,
                datasets_processed=processed,
                local_paths=local_paths,
                merged_dataframe=None,
                join_strategy=self._as_strategy(join_strategy),
                warnings=warnings,
                errors=errors,
                execution_time=elapsed,
                topics_requested=topics,
                topics_succeeded=[],
                topics_failed=[p.topic for p in processed if p.status == DatasetExecStatus.FAILED],
            )

        # 3) Schema alignment
        alignment = self._aligner.align(
            frames,
            topics=frame_topics,
            profiles=frame_profiles,
        )
        warnings.extend(alignment.warnings)

        # 4) Merge
        try:
            merge_result = self._merger.merge(
                alignment.aligned_frames,
                strategy=join_strategy,
                join_keys=alignment.join_keys,
                alignment=alignment,
                topics=frame_topics,
            )
            warnings.extend(merge_result.warnings)
            merged = merge_result.dataframe
            effective_strategy = merge_result.strategy
            join_keys = list(merge_result.join_keys)
        except Exception as exc:
            msg = f"Dataset merge failed: {exc}"
            logger.warning(msg)
            errors.append(msg)
            # Fallback: first frame only
            merged = alignment.aligned_frames[0] if alignment.aligned_frames else None
            effective_strategy = JoinStrategy.AUTO
            join_keys = list(alignment.join_keys)
            if merged is not None:
                warnings.append("Returning first aligned dataset after merge failure.")

        elapsed = time.perf_counter() - started
        success = merged is not None and not any(
            p.status == DatasetExecStatus.FAILED and not p.optional for p in processed
        )

        if merged is None:
            success = False
            if not errors:
                errors.append("Merge produced no DataFrame.")

        result = ExecutionResult(
            success=success,
            datasets_processed=processed,
            local_paths=[p.local_path for p in loadable if p.local_path],
            merged_dataframe=merged,
            join_strategy=effective_strategy,
            join_keys=join_keys,
            schema_alignment=alignment.to_dict(),
            warnings=warnings,
            errors=errors,
            execution_time=elapsed,
            topics_requested=topics,
            topics_succeeded=[p.topic for p in loadable],
            topics_failed=[p.topic for p in processed if p.status == DatasetExecStatus.FAILED],
        )
        logger.info(
            "ExecutionEngine complete",
            extra={
                "success": result.success,
                "n_ok": len(result.topics_succeeded),
                "n_fail": len(result.topics_failed),
                "strategy": result.join_strategy.value
                if isinstance(result.join_strategy, JoinStrategy)
                else result.join_strategy,
                "seconds": round(elapsed, 3),
            },
        )
        return result

    def process_one(
        self,
        request: DatasetRequest | dict[str, Any],
        *,
        optional: bool = True,
    ) -> ProcessedDataset:
        """
        Execute retrieve → acquire → profile → learn for a single DatasetRequest.

        Isolated unit of work — safe to call concurrently in a future parallel
        executor without changing the public execute() API.
        """
        req = self._coerce_request(request)
        topic = req.normalized_topic()
        item = ProcessedDataset(topic=topic, optional=optional)

        if not topic:
            item.status = DatasetExecStatus.FAILED
            item.error = "Empty topic in DatasetRequest"
            return item

        # --- Retrieve ---
        try:
            retrieval = self._do_retrieve(req)
            item.retrieval = _to_dict(retrieval)
        except Exception as exc:
            item.status = DatasetExecStatus.FAILED
            item.error = f"Retrieval failed: {exc}"
            logger.warning(item.error, extra={"topic": topic})
            return item

        status = _retrieval_status(retrieval)
        local_path = _get(retrieval, "local_path")
        download_url = _get(retrieval, "download_url")
        next_action = _get(retrieval, "next_action")

        # Hard miss
        if status in {
            RetrievalStatus.NOT_FOUND.value,
            RetrievalStatus.SEARCH_REQUIRED.value,
            "NOT_FOUND",
            "SEARCH_REQUIRED",
        } and not local_path and not download_url:
            item.status = DatasetExecStatus.FAILED
            item.error = _get(retrieval, "reason") or f"No dataset found for topic '{topic}'"
            return item

        # --- Acquire if needed ---
        needs_acquire = self._needs_acquire(status, local_path, download_url, next_action)
        if needs_acquire:
            try:
                acquisition = self._do_acquire(retrieval)
                item.acquisition = _to_dict(acquisition)
                if not _get(acquisition, "success", False):
                    errs = _get(acquisition, "errors") or ["Acquisition failed"]
                    item.status = DatasetExecStatus.FAILED
                    item.error = "; ".join(str(e) for e in errs)
                    return item
                local_path = _get(acquisition, "local_path") or local_path
                item.dataset_id = _get(acquisition, "dataset_id") or _get(retrieval, "dataset_id")
            except Exception as exc:
                item.status = DatasetExecStatus.FAILED
                item.error = f"Acquisition failed: {exc}"
                logger.warning(item.error, extra={"topic": topic})
                return item
        else:
            # Local file already available
            if local_path and Path(str(local_path)).is_file():
                item.dataset_id = _get(retrieval, "dataset_id")
            elif download_url and not local_path:
                # Should have been acquired; treat as failure
                item.status = DatasetExecStatus.FAILED
                item.error = f"Download URL present but acquisition was not run for '{topic}'"
                return item
            elif not local_path or not Path(str(local_path)).is_file():
                item.status = DatasetExecStatus.FAILED
                item.error = (
                    _get(retrieval, "reason")
                    or f"No usable local path for topic '{topic}'"
                )
                return item

        if not local_path or not Path(str(local_path)).is_file():
            item.status = DatasetExecStatus.FAILED
            item.error = f"Local dataset file missing after pipeline for '{topic}'"
            return item

        item.local_path = str(Path(local_path).resolve())

        # --- Profile (non-fatal) ---
        profile_dict = None
        try:
            profile = self._do_profile(item.local_path)
            profile_dict = _to_dict(profile)
            item.profile = profile_dict
            if profile_dict:
                item.columns = list(profile_dict.get("column_names") or [])
                item.row_count = profile_dict.get("row_count")
        except Exception as exc:
            w = f"Intelligence profiling failed for '{topic}': {exc}"
            item.warnings.append(w)
            logger.warning(w)

        # --- Learn (non-fatal) ---
        try:
            learning = self._do_learn(
                retrieval=item.retrieval or retrieval,
                acquisition=item.acquisition,
                profile=profile_dict,
            )
            learn_dict = _to_dict(learning)
            item.learning = learn_dict
            if learn_dict and learn_dict.get("registry_id"):
                item.dataset_id = item.dataset_id or learn_dict.get("registry_id")
        except Exception as exc:
            w = f"Learning failed for '{topic}': {exc}"
            item.warnings.append(w)
            logger.warning(w)

        item.status = (
            DatasetExecStatus.PARTIAL if item.warnings else DatasetExecStatus.SUCCESS
        )
        return item

    # ------------------------------------------------------------------
    # Dependency resolution (lazy defaults)
    # ------------------------------------------------------------------

    def _do_retrieve(self, req: DatasetRequest) -> Any:
        if self._retrieve is not None:
            return self._retrieve(req)
        from backend.retrieval.service import DatasetRetrievalService

        return DatasetRetrievalService().retrieve(req)

    def _do_acquire(self, retrieval: Any) -> Any:
        if self._acquire is not None:
            return self._acquire(retrieval)
        from backend.acquisition import acquire_dataset

        return acquire_dataset(retrieval)

    def _do_profile(self, local_path: str) -> Any:
        if self._profile is not None:
            return self._profile(local_path)
        from backend.intelligence import profile_dataset

        return profile_dataset(local_path)

    def _do_learn(self, **kwargs: Any) -> Any:
        if self._learn is not None:
            return self._learn(**kwargs)
        from backend.learning import learn_dataset

        return learn_dataset(**kwargs)

    def _load_dataframe(self, local_path: str) -> pd.DataFrame:
        if self._load is not None:
            return self._load(local_path)
        from backend.utils.dataset_loader import load_dataset

        return load_dataset(local_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_requests(
        self,
        requests: Sequence[DatasetRequest | dict[str, Any]],
    ) -> list[DatasetRequest]:
        if requests is None:
            raise ExecutionValidationError("requests is required")
        reqs = list(requests)
        if not reqs:
            raise ExecutionValidationError("At least one DatasetRequest is required")
        if len(reqs) > MAX_DATASETS:
            raise ExecutionValidationError(
                f"Too many datasets ({len(reqs)}); max supported is {MAX_DATASETS}"
            )
        out: list[DatasetRequest] = []
        seen: set[str] = set()
        for r in reqs:
            req = self._coerce_request(r)
            topic = req.normalized_topic()
            if not topic:
                raise ExecutionValidationError("Each DatasetRequest must have a non-empty topic")
            # De-dupe identical topics (keep first)
            key = topic.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(req)
        if not out:
            raise ExecutionValidationError("No valid DatasetRequest topics after normalization")
        return out

    @staticmethod
    def _coerce_request(request: DatasetRequest | dict[str, Any]) -> DatasetRequest:
        if isinstance(request, DatasetRequest):
            return request
        if isinstance(request, dict):
            return DatasetRequest.from_dict(request)
        raise ExecutionValidationError("request must be DatasetRequest or dict")

    @staticmethod
    def _needs_acquire(
        status: Any,
        local_path: Any,
        download_url: Any,
        next_action: Any,
    ) -> bool:
        if local_path and Path(str(local_path)).is_file():
            # Still allow re-validation via acquire which reuses existing
            # Prefer skip for speed when file exists
            return False
        na = next_action.value if hasattr(next_action, "value") else str(next_action or "")
        if na == NextAction.USE_DOWNLOAD_URL.value or na == "USE_DOWNLOAD_URL":
            return bool(download_url)
        st = status.value if hasattr(status, "value") else str(status or "")
        if st in {
            RetrievalStatus.API_HIT.value,
            RetrievalStatus.INTERNET_HIT.value,
            RetrievalStatus.STALE_REGISTRY_ENTRY.value,
            "API_HIT",
            "INTERNET_HIT",
            "STALE_REGISTRY_ENTRY",
        }:
            return bool(download_url)
        if download_url and not (local_path and Path(str(local_path)).is_file()):
            return True
        return False

    @staticmethod
    def _as_strategy(strategy: JoinStrategy | str) -> JoinStrategy:
        if isinstance(strategy, JoinStrategy):
            return strategy
        try:
            return JoinStrategy(str(strategy).lower())
        except ValueError:
            return JoinStrategy.AUTO


def execute_datasets(
    requests: Sequence[DatasetRequest | dict[str, Any]],
    **kwargs: Any,
) -> ExecutionResult:
    """Module-level convenience entrypoint."""
    return ExecutionEngine().execute(requests, **kwargs)


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _to_dict(obj: Any) -> Optional[dict[str, Any]]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {"value": str(obj)}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _retrieval_status(retrieval: Any) -> str:
    status = _get(retrieval, "status")
    if status is None:
        return ""
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)
