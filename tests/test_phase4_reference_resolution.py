"""Phase 4 Regression Tests — LLM Reference Resolution.

Verifies:
1. Active dataset pronouns ('it', 'this') and implicit follow-ups ('show missing values', 'average age')
   are rewritten to explicit queries referencing the active dataset.
2. Visual/Chart references ('explain this', 'what does this show?') are rewritten to reference
   previous chart or operation.
3. The planner receives fully resolved references in state['question'].
"""

from __future__ import annotations

from backend.agents.conversation_context_agent import conversation_context_agent
from backend.utils.reference_resolver import resolve_question_references


def test_active_dataset_reference_resolution():
    """Verify Phase 4 active dataset resolution examples."""
    ds = "titanic.csv"

    # Example 1: "Describe it" -> "Describe the dataset titanic.csv"
    res1 = resolve_question_references("Describe it", dataset_name=ds, has_active_dataset=True)
    assert res1 == "Describe the dataset titanic.csv"

    # Example 2: "Show missing values" -> "Show missing values in dataset titanic.csv"
    res2 = resolve_question_references("Show missing values", dataset_name=ds, has_active_dataset=True)
    assert res2 == "Show missing values in dataset titanic.csv"

    # Example 3: "Average age" -> "Calculate average age in dataset titanic.csv"
    res3 = resolve_question_references("Average age", dataset_name=ds, has_active_dataset=True)
    assert res3 == "Calculate average age in dataset titanic.csv"


def test_previous_chart_and_operation_reference_resolution():
    """Verify Phase 4 visual and operation reference resolution examples."""
    # Example 4: Given previous chart: histogram of Age
    # Question: "Explain this" -> "Explain the histogram of Age chart"
    res4 = resolve_question_references("Explain this", last_chart="histogram of Age", has_active_dataset=True)
    assert res4 == "Explain the histogram of Age chart"

    # Example 5: Given previous operation: correlation matrix
    # Question: "What does this show?" -> "Explain the correlation matrix chart"
    res5 = resolve_question_references("What does this show?", last_operation="correlation matrix", has_active_dataset=True)
    assert res5 == "Explain the correlation matrix chart"


def test_context_agent_rewrites_question_for_planner():
    """Verify conversation_context_agent resolves question references into state['question']."""
    state = {
        "question": "Describe it",
        "dataset_name": "titanic.csv",
        "data": True,
    }
    updated = conversation_context_agent(state)
    assert updated["question"] == "Describe the dataset titanic.csv"
    assert updated["resolved_from_context"] is True
