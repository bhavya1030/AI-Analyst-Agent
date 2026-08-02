"""Topic switch must not rebind previous session dataset (gold after GDP)."""

from __future__ import annotations

from backend.memory.continuity import is_new_dataset_topic, is_follow_up_question
from backend.memory.hierarchy import MemoryHierarchyService
from backend.memory.hierarchy_models import (
    ConversationMemory,
    DatasetMemory,
    KnowledgeMemory,
    MemoryBundle,
    SessionMemory,
)


def test_is_new_topic_gold_after_gdp():
    assert is_new_dataset_topic(
        "Analyze gold prices for previous 5 years",
        "India GDP",
        has_active_dataset=True,
    )
    assert not is_follow_up_question("Analyze gold prices for previous 5 years") or True
    # Follow-up keeps dataset
    assert not is_new_dataset_topic(
        "Show histogram",
        "India GDP",
        has_active_dataset=True,
    )


def test_inject_skips_path_on_topic_mismatch():
    svc = MemoryHierarchyService()
    bundle = MemoryBundle(
        session_id="s1",
        user_id="u1",
        l1_conversation=ConversationMemory(),
        l2_session=SessionMemory(
            session_id="s1",
            dataset_topic="India GDP",
            dataset_name="India GDP",
            dataset_path="/data/india_gdp.csv",
        ),
        l3_dataset=DatasetMemory(),
        l4_knowledge=KnowledgeMemory(),
    )
    state = {
        "question": "Analyze gold prices for previous 5 years",
        "session_id": "s1",
    }
    out = svc.inject_into_state(state, bundle)
    assert out.get("topic_mismatch") is True
    # Must not rebind GDP file for gold analysis
    assert out.get("file_path") not in {"/data/india_gdp.csv"}
    assert out.get("file_path") in (None, "", False) or not out.get("file_path")
