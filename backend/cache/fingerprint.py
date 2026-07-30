"""Dataset content fingerprinting (SHA256) for cache invalidation.

When the underlying dataset bytes or DataFrame content change, the
fingerprint changes and all AnalysisCache entries for the old fingerprint
are automatically orphaned (lookups miss). No explicit delete required.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import pandas as pd

from backend.core.logger import get_logger

logger = get_logger(__name__)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Process-local path fingerprint cache: (resolved_path, size, mtime_ns) → sha256
_FILE_FP_CACHE: dict[str, tuple[int, int, str]] = {}
_FILE_FP_LOCK = __import__("threading").RLock()


def fingerprint_file(path: str | Path) -> Optional[str]:
    """SHA256 of local file contents. Returns None if unreadable/missing.

    Hot-path optimization: if size+mtime are unchanged, reuse the previous digest
    so warm /v1/ask requests do not re-read multi-MB datasets.
    """
    try:
        p = Path(path).expanduser().resolve(strict=False)
        if not p.is_file():
            return None
        stat = p.stat()
        size = int(stat.st_size)
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)))
        cache_key = str(p)
        with _FILE_FP_LOCK:
            cached = _FILE_FP_CACHE.get(cache_key)
            if cached and cached[0] == size and cached[1] == mtime_ns:
                return cached[2]

        h = hashlib.sha256()
        with p.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        # Include size for extra safety against rare hash collisions
        h.update(str(size).encode("utf-8"))
        digest = h.hexdigest()
        with _FILE_FP_LOCK:
            _FILE_FP_CACHE[cache_key] = (size, mtime_ns, digest)
            # Bound memory
            if len(_FILE_FP_CACHE) > 256:
                # drop arbitrary oldest entry
                _FILE_FP_CACHE.pop(next(iter(_FILE_FP_CACHE)))
        return digest
    except Exception as exc:
        logger.debug(
            "File fingerprint failed",
            extra={"path": str(path), "error": str(exc)},
        )
        return None


def clear_file_fingerprint_cache() -> None:
    with _FILE_FP_LOCK:
        _FILE_FP_CACHE.clear()


def fingerprint_dataframe(df: pd.DataFrame) -> str:
    """
    Deterministic SHA256 of DataFrame structure + values.

    Uses pandas' hash_pandas_object so column order, dtypes, and cell
    values all affect the digest.
    """
    if df is None:
        return _sha256_hex(b"empty-dataframe")

    h = hashlib.sha256()
    try:
        h.update(f"shape={df.shape[0]}x{df.shape[1]}".encode("utf-8"))
        h.update("|".join(str(c) for c in df.columns).encode("utf-8"))
        h.update("|".join(str(t) for t in df.dtypes).encode("utf-8"))

        # Content hash — index included so row order matters
        try:
            hashed = pd.util.hash_pandas_object(df, index=True)
            h.update(hashed.to_numpy(dtype="uint64", copy=False).tobytes())
        except Exception:
            # Fallback for mixed / unhashable object columns
            as_str = df.astype(str)
            hashed = pd.util.hash_pandas_object(as_str, index=True)
            h.update(hashed.to_numpy(dtype="uint64", copy=False).tobytes())
    except Exception as exc:
        logger.warning(
            "DataFrame fingerprint fallback",
            extra={"error": str(exc)},
        )
        # Last resort: shape + columns only
        h.update(repr(getattr(df, "shape", None)).encode("utf-8"))
        try:
            h.update("|".join(map(str, df.columns)).encode("utf-8"))
        except Exception:
            pass

    return h.hexdigest()


def _is_remote(reference: str) -> bool:
    if not reference:
        return False
    parsed = urlparse(reference)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def compute_dataset_fingerprint(
    df: Any = None,
    reference: str | None = None,
) -> str:
    """
    Prefer local file content hash when a path is available; otherwise
    hash the in-memory DataFrame. Remote URLs fall back to DataFrame hash
    (optionally mixed with the URL string for identity).
    """
    ref = (reference or "").strip() or None

    if ref and not _is_remote(ref):
        file_fp = fingerprint_file(ref)
        if file_fp:
            return file_fp

    if df is not None and isinstance(df, pd.DataFrame):
        content_fp = fingerprint_dataframe(df)
        if ref and _is_remote(ref):
            # Bind remote identity to content so URL-only collisions are rare
            return _sha256_hex(f"{ref}|{content_fp}".encode("utf-8"))
        return content_fp

    if ref:
        return _sha256_hex(f"ref:{ref}".encode("utf-8"))

    return _sha256_hex(b"unknown-dataset")


def params_hash(params: dict[str, Any] | None) -> str:
    """Stable short hash of cache parameter dict."""
    if not params:
        return "none"
    # Canonical JSON-like serialization without requiring json for non-serializable
    parts: list[str] = []
    for key in sorted(params.keys()):
        value = params[key]
        if isinstance(value, (list, tuple)):
            value = ",".join(str(v) for v in value)
        parts.append(f"{key}={value}")
    raw = "&".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
