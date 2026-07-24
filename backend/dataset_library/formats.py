"""Supported on-disk formats for the Dataset Library.

Add new formats by extending FILE_FORMAT_EXTENSIONS only.
"""

from __future__ import annotations

FILE_FORMAT_EXTENSIONS: dict[str, str] = {
    "csv": ".csv",
    "json": ".json",
    "xlsx": ".xlsx",
    "xls": ".xls",
    "parquet": ".parquet",
}

# Reverse lookup: ".csv" -> "csv"
EXTENSION_TO_FORMAT: dict[str, str] = {
    ext: fmt for fmt, ext in FILE_FORMAT_EXTENSIONS.items()
}


def normalize_format(file_format: str | None) -> str:
    fmt = (file_format or "").strip().lower().lstrip(".")
    if not fmt:
        return "csv"
    # Accept extension-like input
    if fmt in EXTENSION_TO_FORMAT:
        return EXTENSION_TO_FORMAT[fmt]
    if fmt not in FILE_FORMAT_EXTENSIONS:
        # Allow future formats as-is if they look like tokens
        return fmt
    return fmt


def extension_for_format(file_format: str | None) -> str:
    fmt = normalize_format(file_format)
    return FILE_FORMAT_EXTENSIONS.get(fmt, f".{fmt}")


def is_supported_format(file_format: str | None) -> bool:
    fmt = normalize_format(file_format)
    return fmt in FILE_FORMAT_EXTENSIONS


def data_filename(file_format: str | None) -> str:
    """Canonical data file name inside a dataset directory."""
    return f"dataset{extension_for_format(file_format)}"
