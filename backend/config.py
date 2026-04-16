from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings
from pydantic import ConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "sqlite:///memory.db"
    DATA_DIR: Path = BASE_DIR / "data"
    FORECAST_HORIZON: int = 10
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    SIMILARITY_THRESHOLD: int = 55
    CHART_DEFAULT_LIMIT: int = 4
    LOG_LEVEL: str = "INFO"
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
        "inflation": "https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv",
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