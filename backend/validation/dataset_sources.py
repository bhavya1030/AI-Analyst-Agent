"""Dataset Source Validator — health-check configured download URLs.

Validates every known dataset source (config, curated catalog, registry)
for HTTP status, redirects, Content-Type, file format, size, checksum, and
Last-Modified. Produces a machine-readable report for CI and ops.

Broken registry download URLs can be auto-deactivated (is_active=False).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence
from urllib.parse import urlparse

import requests

from backend.acquisition.detection import detect_format_from_bytes
from backend.config import settings
from backend.core.logger import get_logger
from backend.retrieval.data_providers.validation import (
    USER_AGENT,
    is_blocked_url,
    _content_type_ok,
    _is_html_bytes,
)

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 20
MAX_PROBE_BYTES = 512 * 1024
# Minimal tabular payloads (e.g. "a,b\n1,2\n") are valid; reject empty/stub only.
MIN_BYTES = 8
MAX_BYTES = 80 * 1024 * 1024

# Origins that must stay downloadable; catalog_page is advisory (discovery links).
CRITICAL_ORIGINS = frozenset(
    {"config", "catalog", "github_map", "world_bank_map", "registry"}
)
ADVISORY_ORIGINS = frozenset({"catalog_page"})

# Suggested replacements when a known broken pattern appears
REPLACEMENT_MAP: dict[str, str] = {
    "datasets/inflation/master/data/cpi.csv": (
        "https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL.ZG"
        "?format=json&per_page=20000"
    ),
    "data.oecd.org/searchresults": (
        "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD"
        "?format=json&per_page=20000"
    ),
    "datasets/olympics/master/data/summer.csv": (
        "https://raw.githubusercontent.com/rfordatascience/tidytuesday/"
        "master/data/2021/2021-07-27/olympics.csv"
    ),
    "github.com/datasets/gdp/tree": (
        "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv"
    ),
    "github.com/datasets/gdp": (
        "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv"
    ),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SourceEntry:
    """A configured dataset source to validate."""

    key: str
    url: str
    origin: str  # config | catalog | catalog_page | registry | github_map | world_bank_map
    title: str = ""
    expected_format: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceValidationResult:
    key: str
    url: str
    origin: str
    healthy: bool
    status_code: Optional[int] = None
    redirects: int = 0
    final_url: Optional[str] = None
    content_type: Optional[str] = None
    file_format: Optional[str] = None
    file_size: Optional[int] = None
    checksum_sha256: Optional[str] = None
    last_modified: Optional[str] = None
    duration_ms: float = 0.0
    reason: str = ""
    suggested_replacement: Optional[str] = None
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceValidationReport:
    generated_at: str = field(default_factory=_utc_now_iso)
    healthy: list[SourceValidationResult] = field(default_factory=list)
    broken: list[SourceValidationResult] = field(default_factory=list)
    registry_deactivated: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)

    @property
    def critical_broken(self) -> list[SourceValidationResult]:
        """Broken sources that fail CI (downloadable origins only)."""
        return [b for b in self.broken if b.origin in CRITICAL_ORIGINS]

    @property
    def advisory_broken(self) -> list[SourceValidationResult]:
        """Broken discovery/catalog landing pages (reported, non-gating)."""
        return [b for b in self.broken if b.origin in ADVISORY_ORIGINS or b.origin not in CRITICAL_ORIGINS]

    def to_dict(self) -> dict[str, Any]:
        critical = self.critical_broken
        advisory = self.advisory_broken
        return {
            "generated_at": self.generated_at,
            "totals": self.totals
            or {
                "checked": len(self.healthy) + len(self.broken),
                "healthy": len(self.healthy),
                "broken": len(self.broken),
                "critical_broken": len(critical),
                "advisory_broken": len(advisory),
                "registry_deactivated": len(self.registry_deactivated),
            },
            "healthy_sources": [h.to_dict() for h in self.healthy],
            "broken_sources": [b.to_dict() for b in self.broken],
            "critical_broken_sources": [b.to_dict() for b in critical],
            "advisory_broken_sources": [b.to_dict() for b in advisory],
            "suggested_replacements": [
                {
                    "key": b.key,
                    "url": b.url,
                    "suggested_replacement": b.suggested_replacement,
                    "reason": b.reason,
                }
                for b in self.broken
                if b.suggested_replacement
            ],
            "registry_deactivated": self.registry_deactivated,
        }

    @property
    def ok(self) -> bool:
        """True when no critical downloadable sources are broken."""
        return len(self.critical_broken) == 0


def suggest_replacement(url: str) -> Optional[str]:
    u = (url or "").lower()
    for needle, replacement in REPLACEMENT_MAP.items():
        if needle.lower() in u:
            return replacement
    # Landing pages → prefer raw github twin when possible
    if "github.com/" in u and "/blob/" in u:
        return u.replace("github.com/", "raw.githubusercontent.com/").replace(
            "/blob/", "/"
        )
    if "github.com/" in u and "/tree/" in u:
        return None
    return None


def collect_configured_sources() -> list[SourceEntry]:
    """Gather every downloadable source from config + catalogs."""
    entries: list[SourceEntry] = []
    seen: set[str] = set()

    def _add(entry: SourceEntry) -> None:
        url = (entry.url or "").strip()
        if not url or url in seen:
            return
        seen.add(url)
        entries.append(entry)

    # settings.DATASET_SOURCES
    for key, url in (getattr(settings, "DATASET_SOURCES", None) or {}).items():
        _add(
            SourceEntry(
                key=f"config.DATASET_SOURCES.{key}",
                url=str(url),
                origin="config",
                title=f"DATASET_SOURCES[{key}]",
            )
        )

    # settings.DATASET_CATALOG (often landing pages — still validate)
    for i, item in enumerate(getattr(settings, "DATASET_CATALOG", None) or []):
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("download_url")
        if not url:
            continue
        _add(
            SourceEntry(
                key=f"config.DATASET_CATALOG[{i}]",
                url=str(url),
                origin="catalog_page",
                title=str(item.get("title") or url)[:120],
            )
        )

    # Curated provider catalog
    try:
        from backend.retrieval.data_providers.catalog import CURATED

        for topic_key, items in (CURATED or {}).items():
            for j, item in enumerate(items or []):
                if item.get("disabled"):
                    continue
                url = item.get("download_url")
                if not url:
                    continue
                _add(
                    SourceEntry(
                        key=f"catalog.{topic_key}[{j}]",
                        url=str(url),
                        origin="catalog",
                        title=str(item.get("title") or topic_key),
                        expected_format=str(item.get("file_format") or "unknown"),
                        metadata={"provider": item.get("provider"), "topic": topic_key},
                    )
                )
    except Exception as exc:
        logger.warning("Failed to load CURATED catalog", extra={"error": str(exc)})

    # Legacy GitHub / World Bank maps
    try:
        from backend.retrieval.sources.github import GITHUB_RAW

        for key, url in (GITHUB_RAW or {}).items():
            if not isinstance(url, str):
                continue
            _add(
                SourceEntry(
                    key=f"github_map.{key}",
                    url=url,
                    origin="github_map",
                    title=f"GitHub raw [{key}]",
                    expected_format="csv",
                )
            )
    except Exception as exc:
        logger.warning("Failed to load GITHUB_RAW", extra={"error": str(exc)})

    try:
        from backend.retrieval.sources.world_bank import WORLD_BANK_RAW

        for key, info in (WORLD_BANK_RAW or {}).items():
            url = info.get("url") if isinstance(info, dict) else None
            if not url:
                continue
            _add(
                SourceEntry(
                    key=f"world_bank_map.{key}",
                    url=str(url),
                    origin="world_bank_map",
                    title=str((info or {}).get("title") or key),
                    expected_format="csv" if str(url).endswith(".csv") else "json",
                )
            )
    except Exception as exc:
        logger.warning("Failed to load WORLD_BANK_RAW", extra={"error": str(exc)})

    return entries


def collect_registry_sources(*, limit: int = 500) -> list[SourceEntry]:
    """Active registry rows with download_url."""
    entries: list[SourceEntry] = []
    try:
        from backend.registry import list_datasets

        for row in list_datasets(limit=limit, active_only=True):
            url = getattr(row, "download_url", None)
            if not url:
                continue
            entries.append(
                SourceEntry(
                    key=f"registry.{row.dataset_id}",
                    url=str(url),
                    origin="registry",
                    title=str(row.title or row.topic or row.dataset_id),
                    expected_format=str(row.file_format or "unknown"),
                    metadata={
                        "dataset_id": row.dataset_id,
                        "topic": row.topic,
                        "checksum": row.checksum,
                        "fingerprint": getattr(row, "fingerprint", None),
                    },
                )
            )
    except Exception as exc:
        logger.warning("Failed to list registry sources", extra={"error": str(exc)})
    return entries


class DatasetSourceValidator:
    """Validate downloadable dataset URLs end-to-end."""

    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
        get: Callable[..., Any] | None = None,
        head: Callable[..., Any] | None = None,
    ):
        self.timeout = timeout
        self._session = session or requests.Session()
        self._get = get
        self._head = head

    def validate_url(
        self,
        url: str,
        *,
        expected_format: str = "unknown",
        expected_checksum: str | None = None,
    ) -> SourceValidationResult:
        """Validate a single URL; returns partial result fields (caller fills key/origin)."""
        t0 = time.perf_counter()
        blocked, why = is_blocked_url(url)
        if blocked:
            return SourceValidationResult(
                key="",
                url=url,
                origin="",
                healthy=False,
                reason=f"blocked_url:{why}",
                suggested_replacement=suggest_replacement(url),
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            )

        # Landing pages that are not direct files
        if not _looks_downloadable(url) and "api." not in url.lower():
            # Still probe — catalog pages often 200 HTML
            pass

        status_code = None
        content_type = None
        redirects = 0
        final_url = url
        last_modified = None
        size_hdr: Optional[int] = None

        try:
            head_fn = self._head or self._session.head
            head = head_fn(
                url,
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                allow_redirects=True,
            )
            status_code = head.status_code
            redirects = len(getattr(head, "history", None) or [])
            final_url = str(getattr(head, "url", None) or url)
            content_type = head.headers.get("Content-Type")
            last_modified = head.headers.get("Last-Modified")
            cl = head.headers.get("Content-Length")
            if cl and str(cl).isdigit():
                size_hdr = int(cl)

            if status_code >= 400 and status_code not in {403, 405, 501}:
                return SourceValidationResult(
                    key="",
                    url=url,
                    origin="",
                    healthy=False,
                    status_code=status_code,
                    redirects=redirects,
                    final_url=final_url,
                    content_type=content_type,
                    last_modified=last_modified,
                    file_size=size_hdr,
                    reason=f"http_status:{status_code}",
                    suggested_replacement=suggest_replacement(url),
                    duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                )
        except Exception as exc:
            logger.info("HEAD failed; trying GET", extra={"url": url, "error": str(exc)})

        # GET probe for body validation
        try:
            get_fn = self._get or self._session.get
            with get_fn(
                url,
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                allow_redirects=True,
                stream=True,
            ) as resp:
                status_code = resp.status_code
                redirects = max(redirects, len(getattr(resp, "history", None) or []))
                final_url = str(getattr(resp, "url", None) or final_url)
                content_type = content_type or resp.headers.get("Content-Type")
                last_modified = last_modified or resp.headers.get("Last-Modified")
                cl = resp.headers.get("Content-Length")
                if cl and str(cl).isdigit():
                    size_hdr = int(cl)

                if status_code >= 400:
                    return SourceValidationResult(
                        key="",
                        url=url,
                        origin="",
                        healthy=False,
                        status_code=status_code,
                        redirects=redirects,
                        final_url=final_url,
                        content_type=content_type,
                        last_modified=last_modified,
                        file_size=size_hdr,
                        reason=f"http_status:{status_code}",
                        suggested_replacement=suggest_replacement(url),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )

                ct_ok, ct_reason = _content_type_ok(content_type)
                if not ct_ok:
                    return SourceValidationResult(
                        key="",
                        url=url,
                        origin="",
                        healthy=False,
                        status_code=status_code,
                        redirects=redirects,
                        final_url=final_url,
                        content_type=content_type,
                        last_modified=last_modified,
                        file_size=size_hdr,
                        reason=ct_reason,
                        suggested_replacement=suggest_replacement(url),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )

                if size_hdr is not None and size_hdr > MAX_BYTES:
                    return SourceValidationResult(
                        key="",
                        url=url,
                        origin="",
                        healthy=False,
                        status_code=status_code,
                        redirects=redirects,
                        final_url=final_url,
                        content_type=content_type,
                        last_modified=last_modified,
                        file_size=size_hdr,
                        reason=f"file_too_large:{size_hdr}",
                        suggested_replacement=suggest_replacement(url),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )

                chunks: list[bytes] = []
                total = 0
                hasher = hashlib.sha256()
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    hasher.update(chunk)
                    if total < MAX_PROBE_BYTES:
                        # keep only prefix for format detection
                        remain = MAX_PROBE_BYTES - total
                        chunks.append(chunk[:remain] if remain < len(chunk) else chunk)
                    total += len(chunk)
                    if total >= MAX_PROBE_BYTES and size_hdr and size_hdr > MAX_PROBE_BYTES:
                        # For large files, stop after probe (checksum partial only)
                        break
                    if total >= MAX_BYTES:
                        break

                probe = b"".join(chunks)
                file_size = size_hdr if size_hdr is not None else total
                checksum = hasher.hexdigest() if total <= MAX_PROBE_BYTES else f"partial:{hasher.hexdigest()}"

                if file_size is not None and file_size < MIN_BYTES:
                    return SourceValidationResult(
                        key="",
                        url=url,
                        origin="",
                        healthy=False,
                        status_code=status_code,
                        redirects=redirects,
                        final_url=final_url,
                        content_type=content_type,
                        last_modified=last_modified,
                        file_size=file_size,
                        checksum_sha256=checksum,
                        reason=f"file_too_small:{file_size}",
                        suggested_replacement=suggest_replacement(url),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )

                if _is_html_bytes(probe):
                    return SourceValidationResult(
                        key="",
                        url=url,
                        origin="",
                        healthy=False,
                        status_code=status_code,
                        redirects=redirects,
                        final_url=final_url,
                        content_type=content_type,
                        last_modified=last_modified,
                        file_size=file_size,
                        checksum_sha256=checksum,
                        reason="html_body",
                        suggested_replacement=suggest_replacement(url),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )

                if probe.lstrip().startswith(b"%PDF"):
                    return SourceValidationResult(
                        key="",
                        url=url,
                        origin="",
                        healthy=False,
                        status_code=status_code,
                        redirects=redirects,
                        final_url=final_url,
                        content_type=content_type,
                        file_format="pdf",
                        file_size=file_size,
                        checksum_sha256=checksum,
                        reason="pdf_body",
                        suggested_replacement=suggest_replacement(url),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )

                fmt = detect_format_from_bytes(probe, hint_name=final_url)
                if fmt == "unknown" and expected_format not in {"", "unknown", None}:
                    # soft accept expected API formats
                    if expected_format in {"json", "csv"}:
                        fmt = expected_format
                if fmt == "unknown" and not _looks_downloadable(final_url):
                    return SourceValidationResult(
                        key="",
                        url=url,
                        origin="",
                        healthy=False,
                        status_code=status_code,
                        redirects=redirects,
                        final_url=final_url,
                        content_type=content_type,
                        last_modified=last_modified,
                        file_format=fmt,
                        file_size=file_size,
                        checksum_sha256=checksum,
                        reason="unknown_or_landing_page",
                        suggested_replacement=suggest_replacement(url),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )

                if expected_checksum and not checksum.startswith("partial:"):
                    if checksum.lower() != expected_checksum.lower():
                        return SourceValidationResult(
                            key="",
                            url=url,
                            origin="",
                            healthy=False,
                            status_code=status_code,
                            redirects=redirects,
                            final_url=final_url,
                            content_type=content_type,
                            last_modified=last_modified,
                            file_format=fmt,
                            file_size=file_size,
                            checksum_sha256=checksum,
                            reason="checksum_mismatch",
                            suggested_replacement=suggest_replacement(url),
                            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                        )

                return SourceValidationResult(
                    key="",
                    url=url,
                    origin="",
                    healthy=True,
                    status_code=status_code,
                    redirects=redirects,
                    final_url=final_url,
                    content_type=content_type,
                    last_modified=last_modified,
                    file_format=fmt if fmt != "unknown" else (expected_format or "unknown"),
                    file_size=file_size,
                    checksum_sha256=checksum,
                    reason="ok",
                    duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                )
        except Exception as exc:
            return SourceValidationResult(
                key="",
                url=url,
                origin="",
                healthy=False,
                status_code=status_code,
                redirects=redirects,
                final_url=final_url,
                content_type=content_type,
                last_modified=last_modified,
                file_size=size_hdr,
                reason=f"request_error:{exc}",
                suggested_replacement=suggest_replacement(url),
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            )

    def validate_entry(self, entry: SourceEntry) -> SourceValidationResult:
        result = self.validate_url(
            entry.url,
            expected_format=entry.expected_format,
            expected_checksum=(entry.metadata or {}).get("checksum"),
        )
        result.key = entry.key
        result.origin = entry.origin
        result.title = entry.title
        if not result.healthy and not result.suggested_replacement:
            result.suggested_replacement = suggest_replacement(entry.url)
        logger.info(
            "Source validation",
            extra={
                "key": entry.key,
                "healthy": result.healthy,
                "status_code": result.status_code,
                "format": result.file_format,
                "reason": result.reason,
                "duration_ms": result.duration_ms,
            },
        )
        return result

    def validate_all(
        self,
        sources: Sequence[SourceEntry] | None = None,
        *,
        include_registry: bool = True,
    ) -> SourceValidationReport:
        items = list(sources) if sources is not None else collect_configured_sources()
        if include_registry and sources is None:
            items.extend(collect_registry_sources())

        healthy: list[SourceValidationResult] = []
        broken: list[SourceValidationResult] = []
        for entry in items:
            result = self.validate_entry(entry)
            if result.healthy:
                healthy.append(result)
            else:
                broken.append(result)

        report = SourceValidationReport(healthy=healthy, broken=broken)
        report.totals = {
            "checked": len(healthy) + len(broken),
            "healthy": len(healthy),
            "broken": len(broken),
            "critical_broken": len(report.critical_broken),
            "advisory_broken": len(report.advisory_broken),
            "registry_deactivated": 0,
        }
        return report


def _looks_downloadable(url: str) -> bool:
    lower = (url or "").lower().split("?")[0]
    if any(lower.endswith(ext) for ext in (".csv", ".json", ".xlsx", ".xls", ".parquet", ".zip", ".gz")):
        return True
    if "api.worldbank.org" in lower and "format=json" in (url or "").lower():
        return True
    if "api.coingecko.com" in lower:
        return True
    if "raw.githubusercontent.com" in lower:
        return True
    if "/sdmx-json/data/" in lower:
        return True
    return False


def deactivate_broken_registry_urls(
    broken: Sequence[SourceValidationResult],
) -> list[dict[str, Any]]:
    """
    Set is_active=False for registry rows whose download_url failed validation.

    Returns list of deactivated dataset_id records.
    """
    deactivated: list[dict[str, Any]] = []
    try:
        from backend.registry import get_by_dataset_id, update_dataset
    except Exception as exc:
        logger.warning("Registry unavailable for deactivation", extra={"error": str(exc)})
        return deactivated

    for item in broken:
        if item.origin != "registry" and not str(item.key).startswith("registry."):
            continue
        dataset_id = None
        if str(item.key).startswith("registry."):
            dataset_id = str(item.key).split(".", 1)[1]
        if not dataset_id:
            continue
        try:
            row = get_by_dataset_id(dataset_id)
            if row is None:
                continue
            payload = row.to_dict()
            payload["is_active"] = False
            # Annotate summary for operators
            note = f"[AUTO-DISABLED {_utc_now_iso()}] broken source: {item.reason}"
            payload["summary"] = f"{(row.summary or '').strip()}\n{note}".strip()
            if item.suggested_replacement:
                payload["summary"] += f"\nSuggested: {item.suggested_replacement}"
            update_dataset(payload)
            deactivated.append(
                {
                    "dataset_id": dataset_id,
                    "url": item.url,
                    "reason": item.reason,
                    "suggested_replacement": item.suggested_replacement,
                }
            )
            logger.info(
                "Registry source auto-deactivated",
                extra={"dataset_id": dataset_id, "reason": item.reason},
            )
        except Exception as exc:
            logger.warning(
                "Failed to deactivate registry source",
                extra={"dataset_id": dataset_id, "error": str(exc)},
            )
    return deactivated


def generate_validation_report(
    report: SourceValidationReport,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Write JSON + Markdown validation reports to disk."""
    out = Path(output_dir or (Path(settings.DATA_DIR) / "validation_reports"))
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out / f"dataset_sources_{stamp}.json"
    md_path = out / f"dataset_sources_{stamp}.md"
    latest_json = out / "dataset_sources_latest.json"
    latest_md = out / "dataset_sources_latest.md"

    payload = report.to_dict()
    text = json.dumps(payload, indent=2)
    json_path.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    lines = [
        "# Dataset Source Validation Report",
        "",
        f"**Generated (UTC):** {report.generated_at}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| Checked | {payload['totals']['checked']} |",
        f"| Healthy | {payload['totals']['healthy']} |",
        f"| Broken | {payload['totals']['broken']} |",
        f"| Critical broken (CI gate) | {payload['totals'].get('critical_broken', 0)} |",
        f"| Advisory broken (catalog pages) | {payload['totals'].get('advisory_broken', 0)} |",
        f"| Registry deactivated | {payload['totals'].get('registry_deactivated', 0)} |",
        "",
        "## Healthy Sources",
        "",
    ]
    if not report.healthy:
        lines.append("_None_")
    else:
        lines.append("| Key | Format | Size | Status | URL |")
        lines.append("|-----|--------|-----:|-------:|-----|")
        for h in report.healthy:
            lines.append(
                f"| `{h.key}` | {h.file_format or '—'} | {h.file_size or '—'} | "
                f"{h.status_code or '—'} | `{h.url[:80]}` |"
            )

    lines += ["", "## Broken Sources", ""]
    if not report.broken:
        lines.append("_None_")
    else:
        lines.append("| Key | Reason | Suggested Replacement | URL |")
        lines.append("|-----|--------|----------------------|-----|")
        for b in report.broken:
            repl = b.suggested_replacement or "—"
            lines.append(
                f"| `{b.key}` | {b.reason} | `{repl[:60]}` | `{b.url[:70]}` |"
            )

    lines += ["", "## Suggested Replacements", ""]
    repls = payload.get("suggested_replacements") or []
    if not repls:
        lines.append("_None_")
    else:
        for r in repls:
            lines.append(f"- **{r['key']}**: `{r['url']}` → `{r['suggested_replacement']}`")

    md = "\n".join(lines) + "\n"
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    return {
        "json": json_path,
        "markdown": md_path,
        "latest_json": latest_json,
        "latest_markdown": latest_md,
    }


def run_validation(
    *,
    include_registry: bool = True,
    deactivate_registry: bool = False,
    output_dir: str | Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> SourceValidationReport:
    """Run full validation, optional registry cleanup, write report files."""
    validator = DatasetSourceValidator(timeout=timeout)
    report = validator.validate_all(include_registry=include_registry)
    if deactivate_registry and report.broken:
        deactivated = deactivate_broken_registry_urls(report.broken)
        report.registry_deactivated = deactivated
        report.totals["registry_deactivated"] = len(deactivated)
    paths = generate_validation_report(report, output_dir=output_dir)
    logger.info(
        "Dataset source validation complete",
        extra={
            "healthy": len(report.healthy),
            "broken": len(report.broken),
            "report": str(paths.get("latest_json")),
        },
    )
    return report
