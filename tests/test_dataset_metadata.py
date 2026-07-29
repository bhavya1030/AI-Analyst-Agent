"""Tests for automatic dataset metadata generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.metadata import (
    GeneratedDatasetMetadata,
    generate_and_register_dataset_metadata,
    generate_metadata,
    is_placeholder_label,
    topic_from_columns_and_values,
    topic_from_filename,
    topic_from_question,
)
from backend.metadata.topic_detection import (
    detect_countries_from_values,
    detect_metrics_from_columns,
    prefer_non_placeholder,
)


def test_india_gdp_filename_and_columns(tmp_path):
    path = tmp_path / "india_gdp.csv"
    path.write_text(
        "Country,Year,GDP\n"
        "India,2019,2.8e12\n"
        "India,2020,2.7e12\n"
        "India,2021,3.1e12\n",
        encoding="utf-8",
    )
    meta = generate_metadata(local_path=path)
    assert not is_placeholder_label(meta.title)
    assert "India" in meta.title or "india" in meta.title.lower()
    assert "GDP" in meta.title.upper() or "gdp" in meta.title.lower()
    assert meta.domain in {"economics", "finance", "general"}
    assert meta.time_column in {"Year", "year"}
    assert meta.primary_entity in {"Country", "country"}
    assert meta.metrics
    assert any("GDP" in str(m).upper() or "gdp" in str(m).lower() for m in meta.metrics)
    assert meta.country
    assert any("India" in c for c in meta.country)
    assert meta.tags
    assert meta.keywords
    assert meta.summary
    assert meta.description
    assert "user provided" not in meta.title.lower()


def test_topic_from_question_india_gdp():
    topic = topic_from_question("Analyze India's GDP growth over the last decade")
    assert topic
    assert "gdp" in topic.lower() or "GDP" in topic
    assert "india" in topic.lower() or "India" in topic


def test_topic_from_filename():
    assert "GDP" in topic_from_filename("india_gdp.csv").upper() or "gdp" in topic_from_filename(
        "india_gdp.csv"
    ).lower()
    assert topic_from_filename("random_upload_file.csv")


def test_topic_from_columns_values():
    topic = topic_from_columns_and_values(
        ["Country", "Year", "GDP"],
        sample_values=["India", "India", "China"],
        filename="upload.csv",
    )
    assert "India" in topic or "GDP" in topic.upper() or "gdp" in topic.lower()


def test_detect_metrics_and_countries():
    metrics = detect_metrics_from_columns(["Country", "Year", "GDP", "Inflation_Rate"])
    assert any("GDP" in m.upper() for m in metrics)
    countries = detect_countries_from_values(["India", "United States", "foo"])
    assert "India" in countries
    assert "United States" in countries


def test_placeholder_helpers():
    assert is_placeholder_label("user provided dataset")
    assert is_placeholder_label("User Provided Dataset")
    assert not is_placeholder_label("India GDP")
    assert prefer_non_placeholder("user provided dataset", "India GDP") == "India GDP"


def test_data_agent_sets_human_title(tmp_path):
    path = tmp_path / "india_gdp.csv"
    path.write_text(
        "Country,Year,GDP\nIndia,2020,1e12\nIndia,2021,1.1e12\n",
        encoding="utf-8",
    )
    from backend.agents.data_agent import data_agent

    with patch("backend.metadata.service.DatasetMetadataService.register", side_effect=lambda m, **k: m):
        state = data_agent({"file_path": str(path), "question": "analyze this"})
    assert state.get("data") is not None
    assert not is_placeholder_label(state.get("dataset_topic"))
    assert not is_placeholder_label(state.get("dataset_name"))
    assert "GDP" in (state.get("dataset_name") or "").upper() or "gdp" in (
        state.get("dataset_name") or ""
    ).lower()


def test_generate_and_register_applies_state(tmp_path):
    path = tmp_path / "china_population.csv"
    path.write_text(
        "Country,Year,Population\nChina,2010,1.3e9\nChina,2020,1.4e9\n",
        encoding="utf-8",
    )
    state: dict = {
        "file_path": str(path),
        "source": "user_upload",
        "question": "explore population",
        "dataset_topic": "user provided dataset",
    }
    fake_result = MagicMock()
    fake_result.to_dict.return_value = {
        "registry_id": "reg-123",
        "action_taken": "CREATED",
        "metadata_snapshot": {"title": "China Population"},
    }
    with patch("backend.learning.learn_dataset", return_value=fake_result):
        meta = generate_and_register_dataset_metadata(state, local_path=path, register=True)

    assert meta.dataset_id == "reg-123"
    assert state.get("dataset_id") == "reg-123"
    assert not is_placeholder_label(state.get("dataset_topic"))
    assert state.get("dataset_name")
    assert state.get("dataset_metadata", {}).get("title")
    assert "user provided" not in (state.get("dataset_name") or "").lower()


def test_generated_metadata_to_registry_dict():
    meta = GeneratedDatasetMetadata(
        title="India GDP",
        topic="India GDP",
        description="India GDP dataset",
        domain="economics",
        country=["India"],
        metrics=["GDP"],
        time_column="Year",
        primary_entity="Country",
        tags=["economics", "India", "GDP"],
        keywords=["india", "gdp"],
        summary="India GDP | Countries: India",
        columns=["Country", "Year", "GDP"],
        row_count=10,
    )
    payload = meta.to_registry_dict()
    assert payload["title"] == "India GDP"
    assert payload["domain"] == "economics"
    assert payload["country"] == ["India"]
    assert payload["metrics"] == ["GDP"]
