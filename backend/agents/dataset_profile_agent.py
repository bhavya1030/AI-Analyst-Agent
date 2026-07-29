import pandas as pd

from backend.cache.analysis_cache import KIND_EMBEDDING, KIND_PROFILE, get_analysis_cache
from backend.cache.dataset_cache import (
    get_embeddings,
    get_profile,
    remember_fingerprint,
    set_embeddings,
    set_profile,
)
from backend.cache.fingerprint import compute_dataset_fingerprint
from backend.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)


def _is_time_column(df, column_name):
    column = df[column_name]
    normalized_name = column_name.lower().replace("-", "_").replace(" ", "_")
    tokens = set(normalized_name.split("_"))

    if pd.api.types.is_datetime64_any_dtype(column):
        return True

    if {"date", "time", "timestamp"} & tokens:
        return True

    if "year" in tokens and pd.api.types.is_numeric_dtype(column):
        values = pd.to_numeric(column.dropna(), errors="coerce")
        values = values[(values >= 1800) & (values <= 2100)]
        return len(values) >= 2 and values.nunique() >= 2

    if "month" in tokens and pd.api.types.is_numeric_dtype(column):
        values = pd.to_numeric(column.dropna(), errors="coerce")
        return values.between(1, 12).all() if not values.empty else False

    if "day" in tokens and pd.api.types.is_numeric_dtype(column):
        values = pd.to_numeric(column.dropna(), errors="coerce")
        return values.between(1, 31).all() if not values.empty else False

    return False


def _build_profile(df) -> dict:
    profile = {}

    profile["rows"] = int(df.shape[0])
    profile["columns"] = int(df.shape[1])
    profile["column_names"] = df.columns.tolist()

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(exclude="number").columns.tolist()

    profile["numeric_columns"] = numeric_cols
    profile["categorical_columns"] = categorical_cols

    time_columns = []
    for col in df.columns:
        if _is_time_column(df, col):
            time_columns.append(col)
    profile["time_columns"] = time_columns

    profile["missing_values"] = df.isnull().sum().to_dict()

    recommendations = []
    if len(numeric_cols) >= 2:
        recommendations.append("correlation heatmap")
    if len(numeric_cols) >= 1:
        recommendations.append("distribution plot")
    if len(time_columns) >= 1:
        recommendations.append("trend analysis")
    if len(categorical_cols) >= 1:
        recommendations.append("category comparison")
    profile["recommended_analyses"] = recommendations
    return profile


def _profile_embedding_text(profile: dict) -> str:
    parts = [
        " ".join(str(c) for c in (profile.get("column_names") or [])),
        "numeric:" + ",".join(profile.get("numeric_columns") or []),
        "categorical:" + ",".join(profile.get("categorical_columns") or []),
        "time:" + ",".join(profile.get("time_columns") or []),
        f"rows:{profile.get('rows')}",
    ]
    return " | ".join(parts)


def _ensure_profile_embedding(fingerprint: str, profile: dict, reference: str | None) -> None:
    """Cache a lightweight embedding of the dataset profile text."""
    model_name = getattr(settings, "EMBEDDING_MODEL_NAME", "hashing-profile")
    existing = get_embeddings(reference, fingerprint=fingerprint, model=model_name)
    if existing is not None:
        return

    try:
        from backend.semantic.embedding_generator import HashingEmbeddingGenerator

        text = _profile_embedding_text(profile)
        vector = HashingEmbeddingGenerator().embed_one(text)
        payload = {
            "model": model_name,
            "text": text[:2000],
            "vector": vector.tolist(),
            "dimension": int(vector.shape[0]),
        }
        set_embeddings(
            reference,
            payload,
            fingerprint=fingerprint,
            model=model_name,
        )
        # Also write via AnalysisCache service for explicit kind tracking
        get_analysis_cache().put(
            KIND_EMBEDDING,
            fingerprint,
            payload,
            params={"model": model_name},
        )
        logger.info(
            "Dataset profile embedding cached",
            extra={"fingerprint": fingerprint[:16], "dimension": payload["dimension"]},
        )
    except Exception as exc:
        logger.debug(
            "Profile embedding cache skipped",
            extra={"error": str(exc)},
        )


def dataset_profile_agent(state):

    df = state.get("data")

    if df is None:
        state["dataset_profile"] = {}
        return state

    reference = state.get("dataset_url") or state.get("file_path") or state.get("local_path")
    fingerprint = state.get("dataset_fingerprint") or compute_dataset_fingerprint(
        df, reference
    )
    state["dataset_fingerprint"] = fingerprint
    if reference:
        remember_fingerprint(reference, fingerprint)

    # 1) Durable fingerprint cache
    cache = get_analysis_cache()
    cached_profile = cache.get(KIND_PROFILE, fingerprint)
    if cached_profile is None and reference:
        # 2) Legacy reference L1 / durable bridge
        cached_profile = get_profile(reference, fingerprint=fingerprint)

    if cached_profile is not None:
        logger.info(
            "Dataset profile served from cache",
            extra={
                "action": "profile_data",
                "dataset": reference,
                "fingerprint": fingerprint[:16],
            },
        )
        state["dataset_profile"] = cached_profile
        state["rows"] = int(df.shape[0])
        state["columns"] = df.columns.tolist()
        state["profile_from_cache"] = True
        _ensure_profile_embedding(fingerprint, cached_profile, reference)
        return state

    profile = _build_profile(df)

    state["dataset_profile"] = profile
    state["rows"] = int(df.shape[0])
    state["columns"] = df.columns.tolist()
    state["profile_from_cache"] = False

    # Durable + L1
    cache.put(KIND_PROFILE, fingerprint, profile)
    set_profile(reference, profile, fingerprint=fingerprint)
    _ensure_profile_embedding(fingerprint, profile, reference)

    logger.info(
        "Dataset profile cached",
        extra={
            "action": "profile_data",
            "dataset": reference,
            "fingerprint": fingerprint[:16],
        },
    )

    return state
