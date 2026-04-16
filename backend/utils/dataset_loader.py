import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from backend.cache.dataset_cache import get_dataset, set_dataset
from backend.core.logger import get_logger

logger = get_logger(__name__)


def _get_suffix(reference: str) -> str:
    parsed = urlparse(reference)
    if parsed.scheme and parsed.netloc:
        return Path(parsed.path).suffix.lower()
    return Path(reference).suffix.lower()


def load_dataset(reference: str) -> pd.DataFrame:
    if not reference:
        logger.error("Dataset reference missing", extra={"action": "load_dataset", "dataset": reference})
        raise ValueError("No dataset reference provided.")

    cached = get_dataset(reference)
    if cached is not None:
        logger.info(
            "Dataset cache hit",
            extra={"action": "cache_hit", "dataset": reference},
        )
        return cached

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
    start_time = time.perf_counter()

    for loader in loaders:
        try:
            df = loader(reference)
            set_dataset(reference, df)
            logger.info(
                "Dataset loaded",
                extra={
                    "action": "load_dataset",
                    "dataset": reference,
                    "loader": loader.__name__,
                    "duration_ms": round((time.perf_counter() - start_time) * 1000, 3),
                },
            )
            return df
        except Exception as exc:
            errors.append(f"{loader.__name__}: {exc}")

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 3)
    message = f"Could not load dataset from '{reference}'. Tried: {', '.join(errors)}"
    logger.error(
        "Dataset loading failed",
        extra={"action": "load_dataset", "dataset": reference, "duration_ms": elapsed_ms, "error": message},
    )
    raise ValueError(message)
