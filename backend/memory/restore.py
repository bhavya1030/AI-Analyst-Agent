"""Restore active dataframe from session bindings (path / URL / fingerprint)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.core.logger import get_logger

logger = get_logger(__name__)


def restore_dataframe(
    *,
    dataset_path: str | None = None,
    dataset_url: str | None = None,
    local_path: str | None = None,
    file_path: str | None = None,
) -> Any:
    """Load a DataFrame from the first usable local path or URL."""
    candidates: list[str] = []
    for ref in (file_path, local_path, dataset_path, dataset_url):
        if ref and str(ref).strip() and str(ref) not in candidates:
            candidates.append(str(ref).strip())

    if not candidates:
        return None

    from backend.utils.dataset_loader import load_dataset

    for ref in candidates:
        try:
            if not ref.startswith(("http://", "https://")):
                p = Path(ref).expanduser()
                if not p.is_file():
                    continue
                ref = str(p.resolve())
            df = load_dataset(ref)
            logger.info(
                "Restored session dataframe",
                extra={"reference": ref, "rows": int(getattr(df, "shape", [0])[0])},
            )
            return df
        except Exception as exc:
            logger.warning(
                "Failed to restore dataframe from reference",
                extra={"reference": ref, "error": str(exc)},
            )
    return None


def apply_restored_frame(state: dict[str, Any], df: Any) -> dict[str, Any]:
    """Attach restored frame + shape metadata onto graph state."""
    if df is None:
        return state
    state["data"] = df
    state["last_dataset"] = df
    state["has_active_dataset"] = True
    state["reuse_active_dataset"] = not bool(state.get("topic_mismatch"))
    try:
        state["rows"] = int(df.shape[0])
        state["columns"] = list(df.columns.tolist())
    except Exception:
        pass
    state["needs_user_data"] = False
    state.pop("data_acquisition_options", None)
    return state
