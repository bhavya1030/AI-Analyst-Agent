"""File type detection and lightweight integrity checks (no pandas)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

SUPPORTED_FORMATS = ("csv", "json", "xlsx", "xls", "parquet", "zip")

_MAGIC = {
    b"PK\x03\x04": "zip",  # also xlsx (zip container)
    b"PAR1": "parquet",
}


def extension_from_url_or_name(name: str | None) -> Optional[str]:
    if not name:
        return None
    # strip query
    clean = name.split("?")[0].split("#")[0]
    suffix = Path(clean).suffix.lower().lstrip(".")
    if suffix in SUPPORTED_FORMATS or suffix in {"csv", "json", "xlsx", "xls", "parquet", "zip"}:
        return suffix
    return None


def detect_format_from_bytes(content: bytes, *, hint_name: str | None = None) -> str:
    """Detect format from magic bytes + name hint. Prefer content when ambiguous."""
    if not content:
        return "unknown"

    head = content[:16]

    # Parquet
    if content[:4] == b"PAR1" or content[-4:] == b"PAR1":
        return "parquet"

    # ZIP / XLSX
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        # Distinguish xlsx vs generic zip
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = [n.lower() for n in zf.namelist()]
                if any(n.endswith("[content_types].xml") for n in names) and any(
                    "xl/" in n for n in names
                ):
                    return "xlsx"
                return "zip"
        except zipfile.BadZipFile:
            return "zip"

    # OLE compound (old xls)
    if head.startswith(b"\xD0\xCF\x11\xE0"):
        return "xls"

    # JSON
    stripped = content.lstrip()
    if stripped[:1] in (b"{", b"["):
        # quick sanity: try decode start
        try:
            sample = stripped[:2000].decode("utf-8", errors="ignore")
            if sample.lstrip().startswith(("{", "[")):
                return "json"
        except Exception:
            pass

    # CSV heuristic
    try:
        text = content[:4096].decode("utf-8", errors="ignore")
        if "," in text or "\t" in text or ";" in text:
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) >= 1:
                return "csv"
    except Exception:
        pass

    hinted = extension_from_url_or_name(hint_name)
    if hinted:
        return hinted
    return "unknown"


def detect_format(content: bytes, *, url: str | None = None, metadata: dict | None = None) -> str:
    meta_fmt = None
    if metadata:
        meta_fmt = (metadata.get("file_format") or metadata.get("format") or "").lower().strip()
        if meta_fmt in SUPPORTED_FORMATS or meta_fmt in {"csv", "json", "xlsx", "xls", "parquet"}:
            # Prefer content detection for zip/xlsx/parquet; trust meta for csv/json if content unclear
            pass

    hint = url
    if metadata and metadata.get("title"):
        hint = hint or str(metadata.get("title"))

    detected = detect_format_from_bytes(content, hint_name=hint)
    if detected != "unknown":
        return detected

    if meta_fmt and meta_fmt not in {"", "unknown"}:
        return meta_fmt

    url_ext = extension_from_url_or_name(url)
    if url_ext:
        return url_ext
    return "unknown"


def validate_content(content: bytes, file_format: str) -> list[str]:
    """Return list of corruption/validation errors (empty if OK)."""
    errors: list[str] = []
    if not content or len(content) == 0:
        errors.append("Empty download (0 bytes).")
        return errors

    if len(content) < 4:
        errors.append("Download too small to be a valid dataset file.")
        return errors

    fmt = (file_format or "unknown").lower()

    if fmt == "zip" or fmt == "xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                bad = zf.testzip()
                if bad is not None:
                    errors.append(f"Corrupted zip member: {bad}")
                if not zf.namelist():
                    errors.append("ZIP archive is empty.")
        except zipfile.BadZipFile:
            errors.append("File is not a valid ZIP/XLSX archive.")
        return errors

    if fmt == "parquet":
        if content[:4] != b"PAR1" and content[-4:] != b"PAR1":
            errors.append("Parquet magic bytes missing (possible corruption).")
        return errors

    if fmt == "json":
        sample = content.lstrip()[:1]
        if sample not in (b"{", b"["):
            # line-delimited json may still be valid; soft check
            try:
                content[:200].decode("utf-8")
            except Exception:
                errors.append("JSON content is not valid UTF-8.")
        return errors

    if fmt == "csv":
        try:
            content[:1024].decode("utf-8")
        except UnicodeDecodeError:
            try:
                content[:1024].decode("latin-1")
            except Exception:
                errors.append("CSV content is not decodable text.")
        return errors

    if fmt == "xls":
        if not content.startswith(b"\xD0\xCF\x11\xE0"):
            errors.append("XLS file missing OLE signature.")
        return errors

    if fmt == "unknown":
        errors.append("Could not detect a supported file format.")

    return errors


def extract_supported_from_zip(content: bytes) -> tuple[bytes, str, str]:
    """
    Extract the best supported member from a ZIP.

    Returns: (member_bytes, detected_format, member_name)
    """
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        members = [n for n in zf.namelist() if not n.endswith("/") and not n.startswith("__MACOSX")]
        priority = (".csv", ".parquet", ".json", ".xlsx", ".xls")
        chosen = None
        for ext in priority:
            for name in members:
                if name.lower().endswith(ext):
                    chosen = name
                    break
            if chosen:
                break
        if not chosen and members:
            chosen = members[0]
        if not chosen:
            raise ValueError("ZIP contains no files")

        data = zf.read(chosen)
        fmt = detect_format_from_bytes(data, hint_name=chosen)
        if fmt == "unknown":
            ext = Path(chosen).suffix.lower().lstrip(".")
            if ext:
                fmt = ext
        return data, fmt, chosen


def filename_from_url(url: str | None) -> str:
    if not url:
        return "dataset"
    path = urlparse(url).path
    name = Path(path).name or "dataset"
    return name.split("?")[0] or "dataset"
