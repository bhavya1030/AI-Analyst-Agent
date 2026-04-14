from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


def _get_suffix(reference: str) -> str:
    parsed = urlparse(reference)
    if parsed.scheme and parsed.netloc:
        return Path(parsed.path).suffix.lower()
    return Path(reference).suffix.lower()


def load_dataset(reference: str) -> pd.DataFrame:
    if not reference:
        raise ValueError("No dataset reference provided.")

    suffix = _get_suffix(reference)
    loaders = []

    if suffix in {".xlsx", ".xls"}:
        loaders.append(pd.read_excel)
    elif suffix == ".json":
        loaders.append(pd.read_json)
    elif suffix == ".parquet":
        loaders.append(pd.read_parquet)

    loaders.append(pd.read_csv)

    errors = []

    for loader in loaders:
        try:
            return loader(reference)
        except Exception as exc:
            errors.append(f"{loader.__name__}: {exc}")

    raise ValueError(
        f"Could not load dataset from '{reference}'. Tried: {', '.join(errors)}"
    )
