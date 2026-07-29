"""Strict dataset URL / payload validation.

Rejects HTML search pages, PDFs, login walls, and non-tabular payloads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from backend.acquisition.detection import detect_format_from_bytes, validate_content
from backend.core.logger import get_logger

logger = get_logger(__name__)

USER_AGENT = "AI-Analyst-Agent/1.0 (dataset-validation)"
DEFAULT_TIMEOUT = 15
MAX_BYTES = 80 * 1024 * 1024  # 80 MB soft cap for acquisition
MIN_BYTES = 32

# URL path patterns that are never datasets
_BLOCKED_PATH_SNIPPETS = (
    "/searchresults",
    "/search?",
    "/search/",
    "/login",
    "/signin",
    "/accounts/login",
    "/auth/",
    "wiki/",
    "/w/index.php",
    "/catalog/dataset/",  # data.gov landing pages without resource id
)

_BLOCKED_HOST_PATHS = {
    # (host_suffix, path_contains)
}

_HTML_MARKERS = (
    b"<!doctype html",
    b"<html",
    b"<head",
    b"<body",
    b"<title",
    b"<meta ",
    b"<script",
)

_PDF_MAGIC = b"%PDF"
_SUPPORTED = {"csv", "json", "xlsx", "xls", "parquet", "zip"}

_ACCEPTABLE_CONTENT_TYPES = (
    "text/csv",
    "application/csv",
    "text/plain",
    "application/json",
    "text/json",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/parquet",
    "application/x-parquet",
    "application/zip",
    "application/octet-stream",
    "binary/octet-stream",
)


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    final_url: Optional[str] = None
    content_type: Optional[str] = None
    status_code: Optional[int] = None
    file_format: Optional[str] = None
    size_bytes: Optional[int] = None
    content: Optional[bytes] = None
    redirects: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "final_url": self.final_url,
            "content_type": self.content_type,
            "status_code": self.status_code,
            "file_format": self.file_format,
            "size_bytes": self.size_bytes,
            "redirects": self.redirects,
            "details": self.details,
        }


def is_blocked_url(url: str | None) -> tuple[bool, str]:
    """Reject known non-file / search / login / HTML landing patterns."""
    if not url or not str(url).strip():
        return True, "empty_url"
    raw = str(url).strip()
    try:
        parsed = urlparse(raw)
    except Exception:
        return True, "unparseable_url"
    if parsed.scheme not in {"http", "https"}:
        return True, f"unsupported_scheme:{parsed.scheme}"
    host = (parsed.netloc or "").lower()
    path_q = f"{parsed.path or ''}?{parsed.query or ''}".lower()
    full = raw.lower()

    for snip in _BLOCKED_PATH_SNIPPETS:
        if snip in full:
            return True, f"blocked_path:{snip}"

    # OECD/HTML catalog search pages
    if "data.oecd.org" in host and "search" in path_q:
        return True, "oecd_search_page"
    if "stats.oecd.org" in host and "/sdmx-json/" not in path_q and not path_q.rstrip("/").endswith((".csv", ".json")):
        # Allow only explicit SDMX-JSON data endpoints
        if "/sdmx-json/data/" not in path_q:
            return True, "oecd_non_data_endpoint"

    # Wikipedia is never a tabular download
    if "wikipedia.org" in host:
        return True, "wikipedia_page"

    # Generic HTML documentation / search
    if re.search(r"/(search|query|find)([/?]|$)", path_q):
        return True, "search_endpoint"

    return False, ""


def looks_like_file_url(url: str | None) -> bool:
    if not url:
        return False
    lower = url.lower().split("?")[0]
    if any(lower.endswith(ext) for ext in (".csv", ".json", ".xlsx", ".xls", ".parquet", ".zip", ".gz")):
        return True
    # World Bank indicator API (JSON)
    if "api.worldbank.org" in lower and "/indicator/" in lower and "format=json" in url.lower():
        return True
    # CoinGecko / JSON APIs with known hosts
    if "api.coingecko.com" in lower:
        return True
    # OWID raw github
    if "raw.githubusercontent.com" in lower:
        return True
    return False


def _content_type_ok(content_type: str | None) -> tuple[bool, str]:
    if not content_type:
        return True, "missing_content_type_allowed"
    ct = content_type.lower().split(";")[0].strip()
    if ct in {"text/html", "application/xhtml+xml"}:
        return False, f"html_content_type:{ct}"
    if ct in {"application/pdf"}:
        return False, "pdf_content_type"
    if any(ct == a or ct.startswith(a) for a in _ACCEPTABLE_CONTENT_TYPES):
        return True, ct
    # Some CDNs use weird types for CSV
    if "csv" in ct or "json" in ct or "excel" in ct or "spreadsheet" in ct or "zip" in ct:
        return True, ct
    # octet-stream handled above; reject remaining document types
    if ct.startswith("text/") and "csv" not in ct and "plain" not in ct and "json" not in ct:
        return False, f"suspicious_text_type:{ct}"
    return True, ct


def _is_html_bytes(content: bytes) -> bool:
    if not content:
        return False
    head = content[:2048].lstrip().lower()
    if head.startswith(_PDF_MAGIC.lower()) if False else head.startswith(b"%pdf"):
        return False
    return any(marker in head for marker in _HTML_MARKERS)


def validate_url_metadata(url: str, *, timeout: int = DEFAULT_TIMEOUT) -> ValidationResult:
    """
    Lightweight pre-download checks: blocked patterns, optional HEAD,
    content-type, status, redirects.
    """
    blocked, why = is_blocked_url(url)
    if blocked:
        return ValidationResult(ok=False, reason=why, final_url=url)

    try:
        head = requests.head(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            allow_redirects=True,
        )
        # Some hosts disallow HEAD
        if head.status_code in {403, 405, 501}:
            return ValidationResult(
                ok=True,
                reason="head_not_supported_defer_get",
                final_url=str(head.url or url),
                status_code=head.status_code,
                redirects=len(head.history or []),
            )
        if head.status_code >= 400:
            return ValidationResult(
                ok=False,
                reason=f"http_status:{head.status_code}",
                final_url=str(head.url or url),
                status_code=head.status_code,
                content_type=head.headers.get("Content-Type"),
                redirects=len(head.history or []),
            )
        ct = head.headers.get("Content-Type")
        ct_ok, ct_reason = _content_type_ok(ct)
        if not ct_ok:
            return ValidationResult(
                ok=False,
                reason=ct_reason,
                final_url=str(head.url or url),
                status_code=head.status_code,
                content_type=ct,
                redirects=len(head.history or []),
            )
        size_hdr = head.headers.get("Content-Length")
        size = int(size_hdr) if size_hdr and size_hdr.isdigit() else None
        if size is not None and size > MAX_BYTES:
            return ValidationResult(
                ok=False,
                reason=f"file_too_large:{size}",
                final_url=str(head.url or url),
                status_code=head.status_code,
                content_type=ct,
                size_bytes=size,
            )
        if size is not None and size < MIN_BYTES:
            return ValidationResult(
                ok=False,
                reason=f"file_too_small:{size}",
                final_url=str(head.url or url),
                status_code=head.status_code,
                content_type=ct,
                size_bytes=size,
            )
        # Reject final URL if redirect landed on blocked page
        final = str(head.url or url)
        blocked_final, why_final = is_blocked_url(final)
        if blocked_final:
            return ValidationResult(
                ok=False,
                reason=f"redirect_blocked:{why_final}",
                final_url=final,
                status_code=head.status_code,
                content_type=ct,
                redirects=len(head.history or []),
            )
        return ValidationResult(
            ok=True,
            reason="head_ok",
            final_url=final,
            status_code=head.status_code,
            content_type=ct,
            size_bytes=size,
            redirects=len(head.history or []),
        )
    except Exception as exc:
        # Network errors on HEAD are not fatal — GET may still work
        logger.info(
            "HEAD validation deferred",
            extra={"url": url, "error": str(exc)},
        )
        return ValidationResult(ok=True, reason=f"head_error_defer_get:{exc}", final_url=url)


def validate_download_payload(
    content: bytes,
    *,
    url: str | None = None,
    content_type: str | None = None,
    status_code: int | None = None,
) -> ValidationResult:
    """Validate bytes after GET: magic bytes, format, reject HTML/PDF."""
    if status_code is not None and status_code >= 400:
        return ValidationResult(
            ok=False,
            reason=f"http_status:{status_code}",
            final_url=url,
            status_code=status_code,
            content_type=content_type,
            size_bytes=len(content or b""),
        )
    if not content:
        return ValidationResult(ok=False, reason="empty_body", final_url=url, content_type=content_type)

    size = len(content)
    if size < MIN_BYTES:
        return ValidationResult(
            ok=False,
            reason=f"file_too_small:{size}",
            final_url=url,
            content_type=content_type,
            size_bytes=size,
        )
    if size > MAX_BYTES:
        return ValidationResult(
            ok=False,
            reason=f"file_too_large:{size}",
            final_url=url,
            content_type=content_type,
            size_bytes=size,
        )

    ct_ok, ct_reason = _content_type_ok(content_type)
    if not ct_ok:
        return ValidationResult(
            ok=False,
            reason=ct_reason,
            final_url=url,
            content_type=content_type,
            size_bytes=size,
        )

    if content.lstrip().startswith(b"%PDF") or content[:4] == _PDF_MAGIC:
        return ValidationResult(
            ok=False,
            reason="pdf_magic",
            final_url=url,
            content_type=content_type,
            size_bytes=size,
        )

    if _is_html_bytes(content):
        return ValidationResult(
            ok=False,
            reason="html_body",
            final_url=url,
            content_type=content_type,
            size_bytes=size,
            details={"snippet": content[:120].decode("utf-8", errors="replace")},
        )

    fmt = detect_format_from_bytes(content, hint_name=url)
    if fmt == "unknown":
        return ValidationResult(
            ok=False,
            reason="unknown_format",
            final_url=url,
            content_type=content_type,
            size_bytes=size,
            file_format=fmt,
        )
    if fmt not in _SUPPORTED and fmt not in {"csv", "json", "xlsx", "xls", "parquet", "zip"}:
        return ValidationResult(
            ok=False,
            reason=f"unsupported_format:{fmt}",
            final_url=url,
            content_type=content_type,
            size_bytes=size,
            file_format=fmt,
        )

    errors = validate_content(content, fmt)
    if errors:
        return ValidationResult(
            ok=False,
            reason=";".join(errors),
            final_url=url,
            content_type=content_type,
            size_bytes=size,
            file_format=fmt,
        )

    return ValidationResult(
        ok=True,
        reason="payload_ok",
        final_url=url,
        content_type=content_type,
        size_bytes=size,
        file_format=fmt,
        content=content,
    )


def probe_download(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    max_probe_bytes: int = 512_000,
) -> ValidationResult:
    """
    Stream a partial GET to validate status/type/magic without full download
    when Content-Length is huge. Falls back to full body for small files.
    """
    blocked, why = is_blocked_url(url)
    if blocked:
        return ValidationResult(ok=False, reason=why, final_url=url)

    meta = validate_url_metadata(url, timeout=timeout)
    if not meta.ok and not str(meta.reason).startswith("head_"):
        return meta

    try:
        with requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            allow_redirects=True,
            stream=True,
        ) as response:
            final = str(response.url or url)
            blocked_final, why_final = is_blocked_url(final)
            if blocked_final:
                return ValidationResult(
                    ok=False,
                    reason=f"redirect_blocked:{why_final}",
                    final_url=final,
                    status_code=response.status_code,
                    redirects=len(response.history or []),
                )
            if response.status_code >= 400:
                return ValidationResult(
                    ok=False,
                    reason=f"http_status:{response.status_code}",
                    final_url=final,
                    status_code=response.status_code,
                    content_type=response.headers.get("Content-Type"),
                    redirects=len(response.history or []),
                )
            ct = response.headers.get("Content-Type")
            ct_ok, ct_reason = _content_type_ok(ct)
            if not ct_ok:
                return ValidationResult(
                    ok=False,
                    reason=ct_reason,
                    final_url=final,
                    status_code=response.status_code,
                    content_type=ct,
                )

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= max_probe_bytes:
                    break
            probe = b"".join(chunks)
            # If server is small, probe is full body
            cl = response.headers.get("Content-Length")
            full_known = cl and cl.isdigit() and int(cl) <= max_probe_bytes
            if full_known or total < max_probe_bytes:
                return validate_download_payload(
                    probe,
                    url=final,
                    content_type=ct,
                    status_code=response.status_code,
                )
            # Partial: only check magic / html
            if _is_html_bytes(probe):
                return ValidationResult(
                    ok=False,
                    reason="html_body",
                    final_url=final,
                    status_code=response.status_code,
                    content_type=ct,
                    size_bytes=int(cl) if cl and cl.isdigit() else total,
                )
            fmt = detect_format_from_bytes(probe, hint_name=final)
            if fmt == "unknown" and not looks_like_file_url(final):
                return ValidationResult(
                    ok=False,
                    reason="unknown_format_partial",
                    final_url=final,
                    status_code=response.status_code,
                    content_type=ct,
                    file_format=fmt,
                )
            return ValidationResult(
                ok=True,
                reason="partial_probe_ok",
                final_url=final,
                status_code=response.status_code,
                content_type=ct,
                file_format=fmt if fmt != "unknown" else None,
                size_bytes=int(cl) if cl and cl.isdigit() else total,
                redirects=len(response.history or []),
            )
    except Exception as exc:
        return ValidationResult(ok=False, reason=f"probe_error:{exc}", final_url=url)
