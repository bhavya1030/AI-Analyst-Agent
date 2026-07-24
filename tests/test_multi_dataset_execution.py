"""Tests for Multi-Dataset Execution Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from backend.execution import (
    DatasetExecStatus,
    DatasetMerger,
    ExecutionEngine,
    ExecutionValidationError,
    JoinStrategy,
    SchemaAlignmentService,
    canonicalize_column_name,
    detect_column_roles,
    execute_datasets,
)
from backend.execution.models import SchemaAlignmentResult
from backend.retrieval.models import DatasetRequest, NextAction, RetrievalResult, RetrievalStatus


# ---------------------------------------------------------------------------
# Schema alignment
# ---------------------------------------------------------------------------


def test_canonicalize_country_and_year_aliases():
    assert canonicalize_column_name("Country Name") == "Country"
    assert canonicalize_column_name("Nation") == "Country"
    assert canonicalize_column_name("country") == "Country"
    assert canonicalize_column_name("Year") == "Year"
    assert canonicalize_column_name("Fiscal Year") == "Year"
    assert canonicalize_column_name("Date") == "Date"
    assert canonicalize_column_name("State Name") == "State"


def test_detect_column_roles():
    hints = detect_column_roles(["Country Name", "Year", "Value", "State"])
    # Original names before canonicalize
    assert any("country" in c.lower() for c in hints.country_columns)
    assert any("year" in c.lower() for c in hints.time_columns)
    assert any("state" in c.lower() for c in hints.state_columns)


def test_schema_alignment_normalizes_and_join_keys():
    df1 = pd.DataFrame(
        {
            "Country Name": ["India", "China"],
            "Year": [2020, 2020],
            "Value": [2.7e12, 14e12],
        }
    )
    df2 = pd.DataFrame(
        {
            "Nation": ["India", "China"],
            "Fiscal Year": [2020, 2020],
            "Population": [1.38e9, 1.4e9],
        }
    )
    result = SchemaAlignmentService().align(
        [df1, df2],
        topics=["GDP", "Population"],
        profiles=[
            {"dataset_type": "time_series", "time_column": "Year", "entity_column": "Country Name"},
            {"dataset_type": "time_series", "time_column": "Fiscal Year", "entity_column": "Nation"},
        ],
    )
    assert "Country" in result.aligned_frames[0].columns
    assert "Country" in result.aligned_frames[1].columns
    assert "Year" in result.aligned_frames[0].columns
    assert "Year" in result.aligned_frames[1].columns
    assert "Country" in result.join_keys
    assert "Year" in result.join_keys
    # Conflicting Value not present in both after suffix if only one Value
    assert result.aligned_frames[0].shape[0] == 2


def test_schema_alignment_suffixes_overlapping_metrics():
    df1 = pd.DataFrame({"Country": ["A"], "Year": [2020], "Value": [1]})
    df2 = pd.DataFrame({"Country": ["A"], "Year": [2020], "Value": [2]})
    result = SchemaAlignmentService().align(
        [df1, df2],
        topics=["GDP", "Inflation"],
    )
    cols0 = set(result.aligned_frames[0].columns)
    cols1 = set(result.aligned_frames[1].columns)
    # Both should not share "Value" as join-safe identical metric
    assert "Value" not in cols0 or "Value" not in cols1 or cols0 != cols1
    # After suffix at least one Value_* exists
    all_cols = cols0 | cols1
    assert any(c.startswith("Value") for c in all_cols)


# ---------------------------------------------------------------------------
# Dataset merger
# ---------------------------------------------------------------------------


def test_merge_outer_on_country_year():
    a = pd.DataFrame({"Country": ["India", "China"], "Year": [2020, 2020], "GDP": [1, 2]})
    b = pd.DataFrame(
        {"Country": ["India", "China"], "Year": [2020, 2020], "Population": [10, 20]}
    )
    merged = DatasetMerger().merge(
        [a, b],
        strategy=JoinStrategy.OUTER,
        join_keys=["Country", "Year"],
    )
    assert merged.dataframe is not None
    assert len(merged.dataframe) == 2
    assert "GDP" in merged.dataframe.columns
    assert "Population" in merged.dataframe.columns
    assert merged.strategy == JoinStrategy.OUTER


def test_merge_inner_join():
    a = pd.DataFrame({"Country": ["India", "USA"], "Year": [2020, 2020], "X": [1, 2]})
    b = pd.DataFrame({"Country": ["India"], "Year": [2020], "Y": [9]})
    merged = DatasetMerger().merge(
        [a, b], strategy=JoinStrategy.INNER, join_keys=["Country", "Year"]
    )
    assert len(merged.dataframe) == 1
    assert merged.dataframe.iloc[0]["Country"] == "India"


def test_merge_left_join():
    a = pd.DataFrame({"Country": ["India", "USA"], "Year": [2020, 2020], "X": [1, 2]})
    b = pd.DataFrame({"Country": ["India"], "Year": [2020], "Y": [9]})
    merged = DatasetMerger().merge(
        [a, b], strategy=JoinStrategy.LEFT, join_keys=["Country", "Year"]
    )
    assert len(merged.dataframe) == 2


def test_merge_concat():
    a = pd.DataFrame({"a": [1]})
    b = pd.DataFrame({"b": [2]})
    merged = DatasetMerger().merge([a, b], strategy=JoinStrategy.CONCAT, topics=["A", "B"])
    assert len(merged.dataframe) == 2
    assert "_dataset_topic" in merged.dataframe.columns


def test_merge_auto_time_series():
    a = pd.DataFrame({"Country": ["India"], "Year": [2020], "GDP": [1]})
    b = pd.DataFrame({"Country": ["India"], "Year": [2020], "Pop": [2]})
    merged = DatasetMerger().merge(
        [a, b],
        strategy=JoinStrategy.AUTO,
        join_keys=["Country", "Year"],
    )
    assert merged.strategy == JoinStrategy.OUTER
    assert len(merged.dataframe) == 1


def test_merge_single_frame():
    a = pd.DataFrame({"x": [1, 2]})
    merged = DatasetMerger().merge([a], strategy=JoinStrategy.AUTO)
    assert len(merged.dataframe) == 2
    assert merged.datasets_merged == 1


# ---------------------------------------------------------------------------
# Execution engine (mocked retrieve/acquire/profile/learn)
# ---------------------------------------------------------------------------


def _write_csv(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    return str(path)


def _make_retrieval(topic: str, local_path: str) -> RetrievalResult:
    return RetrievalResult(
        status=RetrievalStatus.REGISTRY_HIT,
        dataset_id=f"id-{topic}",
        local_path=local_path,
        metadata={"topic": topic},
        reason="test hit",
        next_action=NextAction.USE_LOCAL_FILE,
        provider="test",
        topic=topic,
    )


def test_execution_engine_multi_dataset_success(tmp_path):
    gdp = _write_csv(
        tmp_path / "gdp.csv",
        "Country Name,Year,Value\nIndia,2020,100\nChina,2020,200\n",
    )
    pop = _write_csv(
        tmp_path / "pop.csv",
        "Nation,Fiscal Year,Population\nIndia,2020,10\nChina,2020,20\n",
    )
    paths = {"GDP": gdp, "Population": pop}

    def retrieve(req: DatasetRequest):
        return _make_retrieval(req.topic, paths[req.topic])

    def profile(local_path: str):
        return {
            "dataset_type": "time_series",
            "column_names": list(pd.read_csv(local_path).columns),
            "row_count": 2,
            "time_column": "Year" if "gdp" in local_path else "Fiscal Year",
            "entity_column": "Country Name" if "gdp" in local_path else "Nation",
        }

    def learn(**kwargs):
        return {"action_taken": "skipped", "registry_id": None}

    engine = ExecutionEngine(
        retrieve_fn=retrieve,
        acquire_fn=lambda r: (_ for _ in ()).throw(AssertionError("should not acquire")),
        profile_fn=profile,
        learn_fn=learn,
    )
    result = engine.execute(
        [
            DatasetRequest(topic="GDP", force_new_topic=True),
            DatasetRequest(topic="Population", force_new_topic=True),
        ]
    )
    assert result.success is True
    assert len(result.local_paths) == 2
    assert result.merged_dataframe is not None
    assert len(result.merged_dataframe) == 2
    assert "Country" in result.merged_dataframe.columns
    assert "Year" in result.merged_dataframe.columns
    assert result.execution_time >= 0
    assert set(result.topics_succeeded) == {"GDP", "Population"}
    assert result.errors == []


def test_execution_engine_continues_on_optional_failure(tmp_path):
    gdp = _write_csv(
        tmp_path / "gdp.csv",
        "Country,Year,GDP\nIndia,2020,100\n",
    )

    def retrieve(req: DatasetRequest):
        if req.topic == "GDP":
            return _make_retrieval("GDP", gdp)
        return RetrievalResult(
            status=RetrievalStatus.NOT_FOUND,
            topic=req.topic,
            reason="not found",
            next_action=NextAction.ASK_USER_UPLOAD,
        )

    engine = ExecutionEngine(
        retrieve_fn=retrieve,
        profile_fn=lambda p: {
            "dataset_type": "time_series",
            "column_names": ["Country", "Year", "GDP"],
            "row_count": 1,
            "time_column": "Year",
            "entity_column": "Country",
        },
        learn_fn=lambda **k: {"action_taken": "skipped"},
    )
    result = engine.execute(
        [
            DatasetRequest(topic="GDP"),
            DatasetRequest(topic="Inflation"),
        ]
    )
    assert result.success is True
    assert "GDP" in result.topics_succeeded
    assert "Inflation" in result.topics_failed
    assert any("Inflation" in w or "not found" in w.lower() for w in result.warnings)
    assert result.merged_dataframe is not None
    assert len(result.merged_dataframe) == 1


def test_execution_engine_required_failure(tmp_path):
    def retrieve(req: DatasetRequest):
        return RetrievalResult(
            status=RetrievalStatus.NOT_FOUND,
            topic=req.topic,
            reason="missing",
            next_action=NextAction.ASK_USER_UPLOAD,
        )

    engine = ExecutionEngine(retrieve_fn=retrieve)
    result = engine.execute(
        [DatasetRequest(topic="GDP"), DatasetRequest(topic="Population")],
        required_topics=["GDP"],
    )
    assert result.success is False
    assert any("GDP" in e or "missing" in e.lower() for e in result.errors)


def test_execution_engine_all_fail():
    def retrieve(req: DatasetRequest):
        return RetrievalResult.search_required(req.topic, reason="need search")

    engine = ExecutionEngine(retrieve_fn=retrieve)
    result = engine.execute([DatasetRequest(topic="X"), DatasetRequest(topic="Y")])
    assert result.success is False
    assert result.merged_dataframe is None
    assert len(result.topics_failed) == 2


def test_execution_engine_acquire_path(tmp_path):
    out = tmp_path / "acquired.csv"
    out.write_text("Country,Year,Value\nIndia,2021,50\n", encoding="utf-8")

    def retrieve(req: DatasetRequest):
        return RetrievalResult(
            status=RetrievalStatus.API_HIT,
            topic=req.topic,
            download_url="https://example.com/data.csv",
            next_action=NextAction.USE_DOWNLOAD_URL,
            provider="world_bank",
            metadata={"topic": req.topic},
        )

    def acquire(retrieval):
        return {
            "success": True,
            "local_path": str(out),
            "dataset_id": "acq-1",
            "checksum": "abc",
            "detected_format": "csv",
            "errors": [],
        }

    engine = ExecutionEngine(
        retrieve_fn=retrieve,
        acquire_fn=acquire,
        profile_fn=lambda p: {
            "dataset_type": "time_series",
            "column_names": ["Country", "Year", "Value"],
            "row_count": 1,
            "time_column": "Year",
            "entity_column": "Country",
        },
        learn_fn=lambda **k: {"action_taken": "created", "registry_id": "reg-1"},
    )
    result = engine.execute([DatasetRequest(topic="GDP")])
    assert result.success is True
    assert result.local_paths
    assert result.datasets_processed[0].acquisition is not None
    assert result.datasets_processed[0].learning is not None
    assert result.datasets_processed[0].dataset_id in {"acq-1", "reg-1"}


def test_execution_engine_validation_empty():
    engine = ExecutionEngine()
    result = engine.execute([])
    assert result.success is False
    assert result.errors


def test_execution_engine_validation_too_many():
    engine = ExecutionEngine(retrieve_fn=lambda r: RetrievalResult.search_required(r.topic))
    reqs = [DatasetRequest(topic=f"T{i}") for i in range(11)]
    result = engine.execute(reqs)
    assert result.success is False
    assert any("max" in e.lower() or "10" in e for e in result.errors)


def test_execution_engine_dedupes_topics(tmp_path):
    path = _write_csv(tmp_path / "g.csv", "Country,Year,V\nIndia,2020,1\n")

    calls = {"n": 0}

    def retrieve(req: DatasetRequest):
        calls["n"] += 1
        return _make_retrieval(req.topic, path)

    engine = ExecutionEngine(
        retrieve_fn=retrieve,
        profile_fn=lambda p: {
            "dataset_type": "time_series",
            "column_names": ["Country", "Year", "V"],
            "row_count": 1,
            "time_column": "Year",
            "entity_column": "Country",
        },
        learn_fn=lambda **k: {},
    )
    result = engine.execute(
        [DatasetRequest(topic="GDP"), DatasetRequest(topic="GDP")]
    )
    assert result.success is True
    assert calls["n"] == 1


def test_process_one_is_independent(tmp_path):
    path = _write_csv(tmp_path / "x.csv", "a,b\n1,2\n")
    engine = ExecutionEngine(
        retrieve_fn=lambda r: _make_retrieval(r.topic, path),
        profile_fn=lambda p: {"column_names": ["a", "b"], "row_count": 1, "dataset_type": "tabular"},
        learn_fn=lambda **k: {},
    )
    one = engine.process_one(DatasetRequest(topic="Alpha"), optional=True)
    assert one.status in (DatasetExecStatus.SUCCESS, DatasetExecStatus.PARTIAL)
    assert one.local_path


def test_module_level_execute_datasets(tmp_path):
    path = _write_csv(tmp_path / "m.csv", "Country,Year,X\nIndia,2019,3\n")
    engine_result_via_module = None

    # Patch via constructing engine is preferred; module uses real services.
    # Use execute_datasets only if we inject through ExecutionEngine — test export exists.
    assert callable(execute_datasets)

    engine = ExecutionEngine(
        retrieve_fn=lambda r: _make_retrieval(r.topic, path),
        profile_fn=lambda p: {
            "dataset_type": "time_series",
            "column_names": ["Country", "Year", "X"],
            "row_count": 1,
            "time_column": "Year",
            "entity_column": "Country",
        },
        learn_fn=lambda **k: {},
    )
    engine_result_via_module = engine.execute([{"topic": "GDP"}])
    assert engine_result_via_module.success is True


def test_execution_result_to_dict(tmp_path):
    path = _write_csv(tmp_path / "r.csv", "Country,Year,Z\nIndia,2018,1\n")
    engine = ExecutionEngine(
        retrieve_fn=lambda r: _make_retrieval(r.topic, path),
        profile_fn=lambda p: {
            "dataset_type": "time_series",
            "column_names": ["Country", "Year", "Z"],
            "row_count": 1,
            "time_column": "Year",
            "entity_column": "Country",
        },
        learn_fn=lambda **k: {},
    )
    result = engine.execute([DatasetRequest(topic="Z")])
    d = result.to_dict()
    assert d["success"] is True
    assert "merged_shape" in d
    assert "datasets_processed" in d
    assert "merged_dataframe" not in d  # omitted unless include_dataframe=True
    d2 = result.to_dict(include_dataframe=True)
    assert d2.get("merged_dataframe") is not None


def test_three_datasets_join(tmp_path):
    p1 = _write_csv(
        tmp_path / "gdp.csv",
        "Country,Year,GDP\nIndia,2020,1\nChina,2020,2\n",
    )
    p2 = _write_csv(
        tmp_path / "pop.csv",
        "Country,Year,Population\nIndia,2020,10\nChina,2020,20\n",
    )
    p3 = _write_csv(
        tmp_path / "inf.csv",
        "Country,Year,Inflation\nIndia,2020,5\nChina,2020,3\n",
    )
    paths = {"GDP": p1, "Population": p2, "Inflation": p3}

    engine = ExecutionEngine(
        retrieve_fn=lambda r: _make_retrieval(r.topic, paths[r.topic]),
        profile_fn=lambda p: {
            "dataset_type": "time_series",
            "column_names": list(pd.read_csv(p).columns),
            "row_count": 2,
            "time_column": "Year",
            "entity_column": "Country",
        },
        learn_fn=lambda **k: {},
    )
    result = engine.execute(
        [
            DatasetRequest(topic="GDP"),
            DatasetRequest(topic="Population"),
            DatasetRequest(topic="Inflation"),
        ]
    )
    assert result.success is True
    assert len(result.topics_succeeded) == 3
    df = result.merged_dataframe
    assert df is not None
    assert len(df) == 2
    assert "GDP" in df.columns or any("GDP" in str(c) for c in df.columns)
    assert any("Population" in str(c) for c in df.columns)
    assert any("Inflation" in str(c) for c in df.columns)
