from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8")

    DATABASE_URL: str = "sqlite:///memory.db"
    DATA_DIR: Path = BASE_DIR / "data"
    FORECAST_HORIZON: int = 10
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    SIMILARITY_THRESHOLD: int = 55
    # Semantic retrieval (cosine / IP on normalized embeddings, 0–1)
    SEMANTIC_SEARCH_TOP_K: int = 5
    # Raised from 0.35 — low floor caused Olympics/Atlantis false semantic hits
    SEMANTIC_MIN_SCORE: float = 0.55
    # Multi-signal registry match threshold (0–1)
    REGISTRY_MIN_CONFIDENCE: float = 0.62
    REGISTRY_SEMANTIC_FLOOR: float = 0.45
    CHART_DEFAULT_LIMIT: int = 4
    OLLAMA_MODEL: str = "qwen3:4b"
    OLLAMA_SERVER_URL: str = "http://localhost:11434"
    LOG_LEVEL: str = "INFO"
    # Local LLM calls are optional. Deterministic routing keeps the copilot responsive.
    USE_LLM_INTENT: bool = False
    USE_LLM_PLANNER: bool = False
    # Topic extraction via Ollama only when rule-based topic is weak/empty.
    # Keep False for snappy UX; set True if you want freer natural-language topics.
    USE_LLM_TOPIC: bool = False
    # Optional LLM refinement of auto-generated dataset titles/descriptions.
    USE_LLM_METADATA: bool = False
    # Persist successful topic→dataset mappings (product memory, not weight training).
    LEARN_DATASETS: bool = True
    # Use Ollama to expand aliases when learning a new dataset topic (can be slow).
    USE_LLM_LEARN: bool = False
    # Phase 7 — automatic conversation summarization
    # Trigger when total messages exceed this count.
    CONVERSATION_SUMMARY_THRESHOLD: int = 20
    # Keep this many most-recent messages verbatim (not folded into summary).
    CONVERSATION_SUMMARY_KEEP_RECENT: int = 12
    # Use Ollama for narrative summary when True; otherwise deterministic extractive.
    USE_LLM_SUMMARY: bool = False
    # Phase 8 — auth preparation (no login UI yet)
    ANONYMOUS_USER_ID: str = "anonymous"
    # When set, Authorization: Bearer <jwt> is validated (HS256). Empty = JWT optional.
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    # Dev / trusted-gateway header accepted when JWT is absent.
    AUTH_USER_HEADER: str = "X-User-Id"
    # If true, reject requests that are still anonymous (strict multi-tenant mode).
    REQUIRE_AUTH: bool = False

    @field_validator("OLLAMA_MODEL", "OLLAMA_SERVER_URL", mode="before")
    def _strip_ollama_strings(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().strip('"').strip("'")
        return value
    DATASET_CATALOG: list[dict[str, Any]] = [
        {
            "title": "World Bank GDP by Country",
            "description": "Annual GDP values for countries from World Bank datasets, suitable for trend and growth analysis.",
            "source": "World Bank",
            "url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
        },
        {
            "title": "World Bank Population by Country",
            "description": "Country-level population totals for demographic and growth analyses.",
            "source": "World Bank",
            "url": "https://data.worldbank.org/indicator/SP.POP.TOTL",
        },
        {
            "title": "US GDP Components Dataset",
            "description": "Gross domestic product breakdown by expenditure components from Data.gov.",
            "source": "Data.gov",
            "url": "https://catalog.data.gov/dataset/us-gdp-components",
        },
        {
            "title": "Global Inflation Rates",
            "description": "Inflation statistics for countries worldwide, useful for macroeconomic comparisons.",
            "source": "Data.gov",
            "url": "https://catalog.data.gov/dataset/global-inflation-rates",
        },
        {
            "title": "GitHub Public CSV of GDP Growth",
            "description": "Community-maintained CSV repository with GDP growth metrics and country-level historical values.",
            "source": "GitHub",
            "url": "https://github.com/datasets/gdp",
        },
        {
            "title": "GitHub CSV of India GDP Growth",
            "description": "Country-specific GDP growth dataset for India sourced from open data repositories.",
            "source": "GitHub",
            "url": "https://github.com/datasets/gdp/tree/main/data",
        },
    ]
    DATASET_SOURCES: dict[str, str] = {
        "gdp": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
        "population": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
        # Direct World Bank indicator JSON (old GitHub cpi.csv path is 404)
        "inflation": (
            "https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL.ZG"
            "?format=json&per_page=20000"
        ),
    }
    MODEL_ROUTING_DEFAULTS: dict[str, Any] = {
        "default_plan": [
            "profile_data",
            "recommend_analysis",
            "dataset_topic_detection",
            "pattern_detection",
            "run_eda",
            "chart_interpretation",
            "hypothesis_generation",
        ],
    }


settings = Settings()