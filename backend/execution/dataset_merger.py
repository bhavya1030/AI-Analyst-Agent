"""Dataset merger — join or concat aligned DataFrames.

Does NOT compute statistics, charts, or EDA.
"""

from __future__ import annotations

from typing import Optional, Sequence

import pandas as pd

from backend.core.logger import get_logger
from backend.execution.exceptions import MergeError
from backend.execution.models import JoinStrategy, MergeResult, SchemaAlignmentResult

logger = get_logger(__name__)


class DatasetMerger:
    """
    Merge multiple aligned datasets.

    Supports: inner, left, outer joins and concat.
    Default strategy AUTO:
      - time-series-like (Country/Year or Date keys) → outer join on keys
      - otherwise entity keys → outer join
      - no keys → concat
    """

    def merge(
        self,
        frames: Sequence[pd.DataFrame],
        *,
        strategy: JoinStrategy | str = JoinStrategy.AUTO,
        join_keys: Optional[Sequence[str]] = None,
        alignment: Optional[SchemaAlignmentResult] = None,
        topics: Optional[Sequence[str]] = None,
    ) -> MergeResult:
        if not frames:
            return MergeResult(
                dataframe=None,
                strategy=self._as_strategy(strategy),
                warnings=["No frames to merge."],
                datasets_merged=0,
            )

        frames = list(frames)
        warnings: list[str] = []
        strategy_enum = self._as_strategy(strategy)

        if alignment is not None:
            keys = list(join_keys) if join_keys is not None else list(alignment.join_keys)
        else:
            keys = list(join_keys or [])

        # Single frame — return as-is
        if len(frames) == 1:
            return MergeResult(
                dataframe=frames[0].copy(),
                strategy=strategy_enum,
                join_keys=keys,
                warnings=warnings,
                datasets_merged=1,
            )

        # Resolve AUTO
        effective = strategy_enum
        if strategy_enum == JoinStrategy.AUTO:
            effective = self._auto_strategy(frames, keys, alignment)
            warnings.append(f"Auto-selected merge strategy: {effective.value}")

        try:
            if effective == JoinStrategy.CONCAT:
                df = self._concat(frames, topics=topics)
            else:
                if not keys:
                    warnings.append(
                        "No join keys available; falling back to concat."
                    )
                    df = self._concat(frames, topics=topics)
                    effective = JoinStrategy.CONCAT
                else:
                    # Validate keys exist
                    missing = []
                    for i, frame in enumerate(frames):
                        for k in keys:
                            if k not in frame.columns:
                                missing.append(f"frame[{i}] missing key '{k}'")
                    if missing:
                        warnings.extend(missing)
                        warnings.append("Join keys incomplete; falling back to concat.")
                        df = self._concat(frames, topics=topics)
                        effective = JoinStrategy.CONCAT
                    else:
                        df = self._join(frames, keys=keys, how=effective.value)
        except Exception as exc:
            logger.warning("Merge failed", extra={"error": str(exc)})
            raise MergeError(str(exc)) from exc

        logger.info(
            "Datasets merged",
            extra={
                "strategy": effective.value,
                "keys": keys,
                "shape": list(df.shape) if df is not None else None,
                "n": len(frames),
            },
        )
        return MergeResult(
            dataframe=df,
            strategy=effective,
            join_keys=list(keys) if effective != JoinStrategy.CONCAT else [],
            warnings=warnings,
            datasets_merged=len(frames),
        )

    def _auto_strategy(
        self,
        frames: Sequence[pd.DataFrame],
        keys: Sequence[str],
        alignment: Optional[SchemaAlignmentResult],
    ) -> JoinStrategy:
        key_set = set(keys)
        # Time series: Country + Year / Date → outer join (preserve sparse years)
        if {"Country", "Year"}.issubset(key_set) or {"Country Code", "Year"}.issubset(key_set):
            return JoinStrategy.OUTER
        if "Year" in key_set or "Date" in key_set:
            return JoinStrategy.OUTER
        if keys:
            # Entity-only join
            return JoinStrategy.OUTER
        return JoinStrategy.CONCAT

    def _join(
        self,
        frames: Sequence[pd.DataFrame],
        *,
        keys: Sequence[str],
        how: str,
    ) -> pd.DataFrame:
        how_norm = how.lower()
        if how_norm not in {"inner", "left", "outer", "right"}:
            raise MergeError(f"Unsupported join how={how}")

        result = frames[0].copy()
        for nxt in frames[1:]:
            # Avoid duplicate key-only issues; pandas suffixes for remaining overlaps
            result = result.merge(
                nxt,
                on=list(keys),
                how=how_norm,
                suffixes=("", "_dup"),
            )
            # Drop accidental _dup keys if any
            dup_cols = [c for c in result.columns if str(c).endswith("_dup")]
            if dup_cols:
                result = result.drop(columns=dup_cols)
        return result

    def _concat(
        self,
        frames: Sequence[pd.DataFrame],
        *,
        topics: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        labeled = []
        for i, df in enumerate(frames):
            piece = df.copy()
            if topics and i < len(topics):
                piece = piece.copy()
                piece.insert(0, "_dataset_topic", topics[i])
            else:
                piece = piece.copy()
                piece.insert(0, "_dataset_topic", f"dataset_{i}")
            labeled.append(piece)
        return pd.concat(labeled, ignore_index=True, sort=False)

    @staticmethod
    def _as_strategy(strategy: JoinStrategy | str) -> JoinStrategy:
        if isinstance(strategy, JoinStrategy):
            return strategy
        try:
            return JoinStrategy(str(strategy).lower())
        except ValueError as exc:
            raise MergeError(f"Unknown join strategy: {strategy}") from exc
