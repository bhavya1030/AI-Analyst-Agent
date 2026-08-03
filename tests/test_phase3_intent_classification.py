"""Phase 3 Regression Tests — LLM-Based Intent Classification.

Verifies:
1. All Phase 3 intent categories (preview, eda, statistics, visualization, qa, forecast, comparison, chart_explanation, dataset_switch, dataset_search, general_chat) are classified accurately.
2. Analytical questions never infer dataset topic or classify as dataset_switch.
3. Legacy intent names map cleanly to standard Phase 3 names.
"""

from __future__ import annotations

from backend.utils.intent_classifier import classify_intents, normalize_intent_name, SUPPORTED_INTENTS


def test_phase3_intent_examples():
    """Verify all 11 required examples from Phase 3 specification."""
    cases = [
        ("show first 5 rows", "preview"),
        ("show missing values", "eda"),
        ("describe dataset", "eda"),
        ("average fare", "statistics"),
        ("plot histogram", "visualization"),
        ("correlation matrix", "visualization"),
        ("forecast passengers", "forecast"),
        ("explain this chart", "chart_explanation"),
        ("analyze GDP", "dataset_switch"),
        ("load iris dataset", "dataset_switch"),
        ("search unemployment dataset", "dataset_search"),
    ]

    for question, expected_intent in cases:
        intents = classify_intents(question)
        assert expected_intent in intents, f"Expected '{expected_intent}' in intents for query '{question}', got {intents}"


def test_analytical_questions_do_not_trigger_dataset_switch():
    """Verify that analytical follow-ups never return dataset_switch or dataset_search."""
    analytical_queries = [
        "show missing values",
        "describe dataset",
        "summary statistics",
        "plot histogram",
        "correlation matrix",
        "average fare",
        "show duplicates",
        "null values count",
        "show first 10 rows",
    ]

    for q in analytical_queries:
        intents = classify_intents(q)
        assert "dataset_switch" not in intents, f"Analytical query '{q}' erroneously triggered dataset_switch: {intents}"
        assert "dataset_search" not in intents, f"Analytical query '{q}' erroneously triggered dataset_search: {intents}"


def test_legacy_intent_mapping():
    """Verify that legacy intent strings normalize to supported Phase 3 names."""
    assert normalize_intent_name("statistical_analysis") == "statistics"
    assert normalize_intent_name("explanation") == "chart_explanation"
    assert normalize_intent_name("forecasting") == "forecast"
    assert normalize_intent_name("dataset_autoload") == "dataset_switch"
