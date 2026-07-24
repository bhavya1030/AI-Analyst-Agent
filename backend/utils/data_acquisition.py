"""Shared helpers for open-data / upload / URL acquisition messaging."""

CONNECT_SOURCES_HINT = (
    "You can still continue by: "
    "(1) uploading a CSV/Excel/JSON/Parquet file, "
    "(2) pasting a direct download URL to a tabular file, or "
    "(3) connecting an open-data source you already have."
)

DEFAULT_ACQUISITION_OPTIONS = [
    {
        "type": "upload",
        "label": "Upload a CSV, Excel, JSON, or Parquet file",
        "how": "Use the upload endpoint or UI dropzone, then ask your analysis question.",
    },
    {
        "type": "direct_url",
        "label": "Paste a direct download URL",
        "how": "Provide a link ending in .csv / .json / .xlsx / .parquet.",
    },
    {
        "type": "connect_source",
        "label": "Connect an external source",
        "how": "Use open portals (data.gov, World Bank, Kaggle, Hugging Face) and paste a raw file URL.",
    },
    {
        "type": "open_search",
        "label": "Ask about a public topic",
        "how": "Try: 'Analyze world GDP', 'Explore COVID cases', or 'Study population growth'.",
    },
]


def build_not_found_message(topic: str | None = None) -> str:
    topic_label = (topic or "").strip() or "this topic"
    return (
        f'I could not find a downloadable open dataset for "{topic_label}". '
        f"{CONNECT_SOURCES_HINT}"
    )


def acquisition_guidance(topic: str | None = None) -> dict:
    return {
        "needs_user_data": True,
        "message": build_not_found_message(topic),
        "data_acquisition_options": list(DEFAULT_ACQUISITION_OPTIONS),
    }
