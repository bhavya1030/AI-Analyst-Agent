from backend.cache.analysis_cache import KIND_EDA, get_analysis_cache
from backend.cache.fingerprint import compute_dataset_fingerprint
from backend.core.logger import get_logger
from backend.utils.json_safe import make_json_safe

logger = get_logger(__name__)


def _compute_eda_summary(df) -> dict:
    summary = {
        "rows": int(df.shape[0]),
        "columns": list(df.columns),
        "missing_values": df.isnull().sum().to_dict(),
        "describe": df.describe(include="all").to_dict(),
    }
    return make_json_safe(summary)


class EDAService:
    """Deterministic EDA execution service with durable caching."""

    def run(self, state: dict) -> dict:
        df = state.get("data")

        # SAFETY CHECK: dataset missing
        if df is None:
            state.setdefault("insights", [])
            state["insights"].append({
                "error": "No dataset available for EDA."
            })
            return state

        reference = state.get("dataset_url") or state.get("file_path") or state.get("local_path")
        fingerprint = state.get("dataset_fingerprint") or compute_dataset_fingerprint(
            df, reference
        )
        state["dataset_fingerprint"] = fingerprint

        try:
            cache = get_analysis_cache()
            cached = cache.get(KIND_EDA, fingerprint)
            if cached is not None:
                summary = cached
                state.setdefault("insights", [])
                # Avoid duplicating the same EDA block on every turn
                if summary not in state["insights"]:
                    state["insights"].append(summary)
                state["rows"] = int(summary.get("rows") or df.shape[0])
                state["columns"] = list(summary.get("columns") or df.columns.tolist())
                state["eda_from_cache"] = True
                logger.info(
                    "EDA served from durable cache",
                    extra={
                        "action": "run_eda",
                        "fingerprint": fingerprint[:16],
                        "dataset": reference,
                    },
                )
                return state

            summary = _compute_eda_summary(df)
            cache.put(KIND_EDA, fingerprint, summary)

            state.setdefault("insights", [])
            state["insights"].append(summary)
            state["rows"] = int(df.shape[0])
            state["columns"] = df.columns.tolist()
            state["eda_from_cache"] = False
            logger.info(
                "EDA computed and cached",
                extra={
                    "action": "run_eda",
                    "fingerprint": fingerprint[:16],
                    "dataset": reference,
                },
            )

        except Exception as e:
            state.setdefault("insights", [])
            state["insights"].append({
                "error": f"EDA failed: {str(e)}"
            })

        return state


eda_service = EDAService()


def eda_agent(state: dict) -> dict:
    return eda_service.run(state)
