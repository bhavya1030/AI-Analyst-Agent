import pandas as pd


class CleaningService:
    """Light, non-destructive data cleaning service."""

    def run(self, state: dict) -> dict:
        df = state.get("data")

        if df is None:
            state["answer"] = state.get("answer") or "No dataset available to clean."
            return state

        original_rows = len(df)
        original_cols = len(df.columns)
        cleaned = df.copy()

        cleaned.columns = [str(col).strip() for col in cleaned.columns]
        cleaned = cleaned.dropna(axis=0, how="all")
        cleaned = cleaned.dropna(axis=1, how="all")

        # Drop duplicate full rows when present.
        before_dedupe = len(cleaned)
        cleaned = cleaned.drop_duplicates()
        duplicates_removed = before_dedupe - len(cleaned)

        # Coerce numeric-looking object columns cautiously.
        for col in cleaned.columns:
            if pd.api.types.is_numeric_dtype(cleaned[col]):
                continue
            if cleaned[col].dtype == object:
                sample = cleaned[col].dropna().astype(str).head(50)
                if sample.empty:
                    continue
                numeric_ratio = sample.str.replace(",", "", regex=False).str.match(
                    r"^-?\d+(\.\d+)?$"
                ).mean()
                if numeric_ratio >= 0.8:
                    cleaned[col] = pd.to_numeric(
                        cleaned[col].astype(str).str.replace(",", "", regex=False),
                        errors="coerce",
                    )

        state["data"] = cleaned
        state["cleaned"] = True
        state["rows"] = int(cleaned.shape[0])
        state["columns"] = cleaned.columns.tolist()
        state.setdefault("insights", []).append(
            {
                "cleaning_summary": {
                    "rows_before": original_rows,
                    "rows_after": int(cleaned.shape[0]),
                    "columns_before": original_cols,
                    "columns_after": int(cleaned.shape[1]),
                    "rows_removed": int(original_rows - len(cleaned)),
                    "duplicates_removed": int(duplicates_removed),
                }
            }
        )

        return state


cleaning_service = CleaningService()


def cleaning_agent(state: dict) -> dict:
    return cleaning_service.run(state)
