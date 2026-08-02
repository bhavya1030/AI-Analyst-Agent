> Phase 2 — Session Architecture Consolidation (2026-08-02)

## Overview

AI-Analyst-Agent uses a single, durable session persistence layer backed by
three SQLite tables managed by `backend/sessions/service.py`.

---

## Database Schema

### `analysis_sessions`
Primary session document. Stores metadata + active dataset binding.

| Column | Type | Purpose |
|---|---|---|
| `session_id` | VARCHAR(128) PK | UUID session identifier |
| `user_id` | VARCHAR(128) | Owner (default: "anonymous") |
| `title` | VARCHAR(512) | Human-readable session name |
| `created_at / updated_at / last_activity_at` | DATETIME | Timestamps |
| `dataset_id / dataset_name / dataset_path / dataset_url / dataset_topic` | VARCHAR | Active dataset binding |
| `last_column / last_columns / last_chart_type / last_intent / last_operation / last_forecast_target / last_query / last_insight / eda_summary` | Various | Continuity fields for follow-up questions |
| `status` | VARCHAR(32) | `active` \| `archived` \| `deleted` |
| `favorite / archived / deleted / pinned` | BOOLEAN | Lifecycle flags |
| `pin_order` | INTEGER | Position when pinned |
| `message_count` | INTEGER | Denormalized count |
| `conversation_summary` | TEXT | Phase 7 durable summary |
| `memory_state` | JSON | L2 session memory blob |

### `session_messages`
Ordered chat history.

| Column | Type | Purpose |
|---|---|---|
| `id` | VARCHAR(36) PK | UUID |
| `session_id` | VARCHAR(128) FK | Parent session |
| `seq` | INTEGER | Order within session |
| `role` | VARCHAR(32) | `user` \| `assistant` \| `system` |
| `content` | TEXT | Message text |
| `payload` | JSON | Structured metadata (artifact_ids, intent, etc.) |
| `is_summarized` | BOOLEAN | Phase 7: folded into conversation_summary |

### `session_artifacts`
Restorable analysis outputs.

| Column | Type | Purpose |
|---|---|---|
| `id` | VARCHAR(36) PK | UUID |
| `session_id` | VARCHAR(128) FK | Parent session |
| `message_id` | VARCHAR(36) FK | Linked assistant message |
| `kind` | VARCHAR(32) | `chart` \| `forecast` \| `eda` \| `profile` \| `insight` \| `hypothesis` \| `analysis_result` |
| `title` | VARCHAR(512) | Human label |
| `content` | JSON | Plotly figure, forecast series, EDA dict, etc. |

---

## Session Lifecycle

```
POST /v1/ask?question=...&session_id=abc
│
├─ SessionService.ensure_session(sid, user_id)      # create if absent
├─ SessionService.append_user_message(sid, question) # persist user turn
│
│  [LangGraph graph runs]
│
├─ SessionService.record_assistant_turn(sid, result) # persist answer + artifacts
├─ MemoryHierarchyService.persist(sid, result)       # update L2/L3 memory blobs
└─ finalize_session_write(sid)                       # read-after-write barrier
```

### Turn Persistence Details
`record_assistant_turn` in a single atomic transaction:
1. Updates dataset binding fields on `analysis_sessions`
2. Updates continuity fields (`last_intent`, `last_chart_type`, etc.)
3. Inserts assistant `SessionMessage`
4. Inserts `SessionArtifact` rows for every chart, forecast, EDA output, insight, hypothesis

### Warm-Path (Cache Hit)
When the ask-level cache has a hit, `record_cached_assistant_turn` is called instead:
1. Updates continuity fields only
2. Inserts a lightweight assistant message with `from_cache: true` payload
3. Does NOT rebuild artifact rows (they already exist from the cold run)

---

## Removed: Legacy `session_memory` Table

Prior to Phase 2 the system maintained a parallel legacy `session_memory` SQLite table.

### What was removed

| Item | Location | Status |
|---|---|---|
| `SessionMemory(Base)` SQLAlchemy model | `backend/db.py` | **Deleted** |
| `EXPECTED_COLUMNS` dict | `backend/db.py` | **Deleted** |
| `ensure_session_memory_schema()` | `backend/db.py` | **Deleted** |
| `get_session(session_id)` | `backend/db.py` | **Deleted** |
| `list_sessions()` | `backend/db.py` | **Deleted** |
| `save_session(session_id, ...)` | `backend/db.py` | **Deleted** |
| `SessionService._dual_write_legacy()` | `sessions/service.py` | **Deleted** |
| `SessionService._migrate_legacy()` | `sessions/service.py` | **Deleted** |
| `SessionService._migrate_all_legacy()` | `sessions/service.py` | **Deleted** |
| 11 `_dual_write_legacy(...)` call sites | `sessions/service.py` | **Removed** |
| `from backend.db import get_session, save_session` | `main.py` | **Removed** |
| Legacy fallback in `/analyze` handler | `main.py` | **Removed** |
| Legacy fallback in `/ask` handler | `main.py` | **Removed** |
| `from backend.db import get_session` | `retrieval/service.py` | **Removed** |
| `test_legacy_session_memory_migrates_on_get` test | `tests/test_session_persistence.py` | **Deleted** |

### Why the table still exists in memory.db

The `session_memory` table is NOT dropped via SQL migration. The application simply
stops reading and writing it. This is intentional:
- No data loss risk during transition
- Existing `memory.db` rows remain available for manual inspection/recovery
- The table becomes orphaned — add `memory.db` to `.gitignore` to prevent future
  accidental commits (tracked separately as a cleanup task)

### Note: `memory/hierarchy_models.py::SessionMemory`

There are TWO classes named `SessionMemory` in this codebase:
- `db.py::SessionMemory(Base)` — the legacy SQLAlchemy ORM model → **deleted**
- `memory/hierarchy_models.py::SessionMemory` — a Python `@dataclass` representing
  L2 session memory in the 4-level hierarchy → **kept and unchanged**

---

## Key Design Invariants

1. **Single writer**: `SessionService` is the only code that writes to `analysis_sessions`.
2. **Atomic turns**: Each `/ask` turn writes session fields + messages + artifacts in one transaction.
3. **Read-after-write**: `finalize_session_write()` verifies the row is visible on a fresh connection before returning the HTTP response.
4. **User isolation**: Every query is scoped to `user_id`. Sessions are not visible across users.
5. **Soft delete by default**: `delete_session(hard=False)` sets `deleted=True`; `hard=True` physically removes rows including cascaded messages and artifacts.
