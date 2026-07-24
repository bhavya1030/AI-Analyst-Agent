"""Resolve dataset candidates to loadable file URLs and lightly validate them."""

from __future__ import annotations

import io
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

from backend.core.logger import get_logger

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = (".csv", ".json", ".xlsx", ".xls", ".parquet")
PROBE_BYTES = 64_000
REQUEST_TIMEOUT = 8


def is_loadable_url(url: str | None) -> bool:
    if not url or not isinstance(url, str):
        return False
    lower = url.lower().split("?")[0]
    if any(lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        return True
    return any(ext in lower for ext in SUPPORTED_EXTENSIONS)


def probe_loadable(url: str, max_rows: int = 20) -> dict[str, Any]:
    """Try to read a small sample from a remote/local tabular URL."""
    if not url:
        return {"ok": False, "columns": [], "rows_sampled": 0, "error": "empty url"}

    try:
        if url.lower().startswith("http"):
            df = _read_remote_sample(url, max_rows=max_rows)
        else:
            df = _read_local_sample(url, max_rows=max_rows)

        if df is None or df.empty:
            return {"ok": False, "columns": [], "rows_sampled": 0, "error": "empty sample"}

        return {
            "ok": True,
            "columns": [str(c) for c in df.columns.tolist()],
            "rows_sampled": int(len(df)),
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "columns": [], "rows_sampled": 0, "error": str(exc)}


def resolve_huggingface_dataset(repo_id: str) -> list[dict[str, Any]]:
    """List tabular file candidates from a Hugging Face dataset repo."""
    if not repo_id:
        return []

    api_url = f"https://huggingface.co/api/datasets/{repo_id}/tree/main"
    candidates: list[dict[str, Any]] = []
    try:
        response = requests.get(api_url, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return []
        entries = response.json()
        if not isinstance(entries, list):
            return []

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path") or ""
            lower = path.lower()
            if not any(lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                continue
            size = entry.get("size") or 0
            raw_url = f"https://huggingface.co/datasets/{repo_id}/resolve/main/{path}"
            candidates.append(
                {
                    "title": f"{repo_id}/{path}",
                    "description": f"Hugging Face file {path}",
                    "source": "Hugging Face",
                    "url": raw_url,
                    "rank_hint": 6 if size and size < 50_000_000 else 3,
                    "file_size": size,
                }
            )
    except Exception as exc:
        logger.warning(
            "Hugging Face tree resolve failed",
            extra={"repo_id": repo_id, "error": str(exc)},
        )
    return candidates


def resolve_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Return a candidate with a preferred loadable URL, or None if unusable for auto-load."""
    if not candidate:
        return None

    url = candidate.get("url") or ""

    if "huggingface.co/datasets/" in url and not is_loadable_url(url):
        repo_id = url.rstrip("/").split("huggingface.co/datasets/")[-1]
        repo_id = repo_id.split("?")[0]
        files = resolve_huggingface_dataset(repo_id)
        if files:
            files_sorted = sorted(
                files,
                key=lambda item: (
                    0 if str(item.get("url", "")).lower().endswith(".csv") else 1,
                    -(item.get("rank_hint") or 0),
                ),
            )
            best_file = files_sorted[0]
            merged = {**candidate, **best_file}
            merged["title"] = candidate.get("title") or best_file.get("title")
            return merged
        return None

    if is_loadable_url(url):
        return candidate

    return None


def prefer_validated(candidates: list[dict[str, Any]], max_probe: int = 5) -> list[dict[str, Any]]:
    """Resolve and optionally probe top candidates; put validated ones first."""
    resolved: list[dict[str, Any]] = []
    for candidate in candidates:
        fixed = resolve_candidate(candidate)
        if fixed is None:
            related = dict(candidate)
            related["loadable"] = False
            related["validated"] = False
            resolved.append(related)
            continue

        fixed = dict(fixed)
        fixed["loadable"] = is_loadable_url(fixed.get("url"))
        fixed["validated"] = False
        resolved.append(fixed)

    probed = 0
    for item in resolved:
        if probed >= max_probe:
            break
        if not item.get("loadable"):
            continue
        result = probe_loadable(item["url"])
        probed += 1
        if result.get("ok"):
            item["validated"] = True
            item["sample_columns"] = result.get("columns") or []
            item["rank_hint"] = int(item.get("rank_hint") or 0) + 8
        else:
            item["validated"] = False
            item["probe_error"] = result.get("error")
            item["rank_hint"] = int(item.get("rank_hint") or 0) - 3

    resolved.sort(
        key=lambda item: (
            1 if item.get("validated") else 0,
            1 if item.get("loadable") else 0,
            int(item.get("rank_hint") or 0),
        ),
        reverse=True,
    )
    return resolved


def looks_like_direct_url(text: str | None) -> bool:
    if not text:
        return False
    parsed = urlparse(text.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _read_remote_sample(url: str, max_rows: int = 20) -> pd.DataFrame:
    headers = {"User-Agent": "AI-Analyst-Agent/1.0"}
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers, stream=True)
    response.raise_for_status()

    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total >= PROBE_BYTES:
            break
    raw = b"".join(chunks)
    lower = url.lower().split("?")[0]

    if lower.endswith(".csv") or ".csv" in lower:
        return pd.read_csv(io.BytesIO(raw), nrows=max_rows)
    if lower.endswith(".json") or ".json" in lower:
        try:
            return pd.read_json(io.BytesIO(raw))
        except Exception:
            return pd.read_json(io.BytesIO(raw), lines=True)
    if lower.endswith((".xlsx", ".xls")):
        full = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
        full.raise_for_status()
        return pd.read_excel(io.BytesIO(full.content), nrows=max_rows)
    if lower.endswith(".parquet"):
        full = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
        full.raise_for_status()
        return pd.read_parquet(io.BytesIO(full.content)).head(max_rows)

    return pd.read_csv(io.BytesIO(raw), nrows=max_rows)


def _read_local_sample(path: str, max_rows: int = 20) -> pd.DataFrame:
    lower = path.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(path, nrows=max_rows)
    if lower.endswith(".json"):
        try:
            return pd.read_json(path)
        except Exception:
            return pd.read_json(path, lines=True)
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(path, nrows=max_rows)
    if lower.endswith(".parquet"):
        return pd.read_parquet(path).head(max_rows)
    return pd.read_csv(path, nrows=max_rows)
