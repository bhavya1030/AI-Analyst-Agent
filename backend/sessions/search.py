"""SQLite FTS5 full-text search for analysis sessions (Phase 4).

Indexes per session:
  - title
  - messages (concatenated chat history)
  - summary (conversation_summary / last_insight)
  - tags

Supports pagination, BM25 ranking, and highlight/snippet generation.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as DbSession

from backend.core.logger import get_logger
from backend.db import SessionLocal, engine
from backend.utils.json_safe import sanitize_for_json

logger = get_logger(__name__)

FTS_TABLE = "session_fts"

# BM25 column weights: title, messages, summary, tags (indexed cols only)
_BM25_WEIGHTS = (10.0, 1.0, 5.0, 3.0)

_fts_lock = threading.Lock()
_fts_ready = False
_fts_available: bool | None = None

# FTS5 reserved tokens / operators to strip from user input
_FTS_SPECIAL = re.compile(r'["\'\*\^\:\(\)\{\}\[\]~]')
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:'[A-Za-z0-9]+)?")


def fts5_available(db_engine: Engine | None = None) -> bool:
    """Return True when this SQLite build has FTS5."""
    global _fts_available
    if _fts_available is not None:
        return _fts_available
    eng = db_engine or engine
    try:
        with eng.connect() as conn:
            # Prefer feature probe over compile-option (more reliable)
            conn.execute(
                text(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe "
                    "USING fts5(x)"
                )
            )
            conn.execute(text("DROP TABLE IF EXISTS _fts5_probe"))
            conn.commit()
        _fts_available = True
    except Exception as exc:
        logger.warning("SQLite FTS5 unavailable; search will use LIKE fallback", extra={"error": str(exc)})
        _fts_available = False
    return bool(_fts_available)


def ensure_session_fts(db_engine: Engine | None = None) -> None:
    """Create FTS5 virtual table if missing (idempotent)."""
    global _fts_ready
    eng = db_engine or engine
    with _fts_lock:
        if _fts_ready:
            return
        if not fts5_available(eng):
            _fts_ready = True
            return
        with eng.begin() as conn:
            conn.execute(
                text(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
                        session_id UNINDEXED,
                        user_id UNINDEXED,
                        title,
                        messages,
                        summary,
                        tags,
                        tokenize = 'porter unicode61'
                    )
                    """
                )
            )
        _fts_ready = True
        logger.info("Session FTS5 index ready", extra={"table": FTS_TABLE})


def build_match_query(q: str) -> str:
    """
    Convert free-text user input into a safe FTS5 MATCH expression.

    Multi-token queries use AND (all terms must match) with prefix matching
    on the last token for incremental-search friendliness.
    """
    raw = (q or "").strip()
    if not raw:
        return ""

    cleaned = _FTS_SPECIAL.sub(" ", raw)
    tokens = _TOKEN_RE.findall(cleaned)
    if not tokens:
        # fallback: quote whole string without operators
        safe = raw.replace('"', " ").strip()
        return f'"{safe}"' if safe else ""

    parts: list[str] = []
    for i, tok in enumerate(tokens):
        # Prefix match on final token for typeahead; exact stems on earlier
        if i == len(tokens) - 1 and len(tok) >= 2:
            parts.append(f'"{tok}"*')
        else:
            parts.append(f'"{tok}"')
    return " AND ".join(parts)


def _tags_text(tags: Any) -> str:
    if not tags:
        return ""
    if isinstance(tags, list):
        return " ".join(str(t) for t in tags if t)
    return str(tags)


def _messages_blob(db: DbSession, session_id: str) -> str:
    rows = db.execute(
        text(
            """
            SELECT role, content FROM session_messages
            WHERE session_id = :sid
            ORDER BY seq ASC
            """
        ),
        {"sid": session_id},
    ).fetchall()
    parts = []
    for role, content in rows:
        body = (content or "").strip()
        if not body:
            continue
        parts.append(f"{role or 'message'}: {body}")
    return "\n".join(parts)


def _load_session_row(db: DbSession, session_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT session_id, user_id, title, tags_json,
                   last_insight, last_query
            FROM analysis_sessions
            WHERE session_id = :sid
            """
        ),
        {"sid": session_id},
    ).mappings().first()
    if not row:
        return None
    data = dict(row)

    # conversation_summary column may not exist on older DBs
    summary = ""
    try:
        sum_row = db.execute(
            text(
                """
                SELECT conversation_summary FROM analysis_sessions
                WHERE session_id = :sid
                """
            ),
            {"sid": session_id},
        ).first()
        if sum_row and sum_row[0]:
            summary = str(sum_row[0])
    except Exception:
        summary = ""

    if not summary:
        # Derive a searchable summary from insight + last query
        insight = (data.get("last_insight") or "").strip()
        query = (data.get("last_query") or "").strip()
        summary = " ".join(p for p in (insight, query) if p)

    tags_raw = data.get("tags_json")
    if isinstance(tags_raw, str):
        try:
            import json

            tags_raw = json.loads(tags_raw)
        except Exception:
            tags_raw = [tags_raw]

    return {
        "session_id": data["session_id"],
        "user_id": data.get("user_id") or "anonymous",
        "title": data.get("title") or "",
        "messages": _messages_blob(db, session_id),
        "summary": summary,
        "tags": _tags_text(tags_raw),
    }


def upsert_session_fts(session_id: str, db: DbSession | None = None) -> None:
    """Rebuild FTS document for one session."""
    ensure_session_fts()
    if not fts5_available():
        return

    sid = (session_id or "").strip()
    if not sid:
        return

    owns_db = db is None
    db = db or SessionLocal()
    try:
        doc = _load_session_row(db, sid)
        # Delete existing rows for session then insert
        db.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE session_id = :sid"),
            {"sid": sid},
        )
        if doc is None:
            db.commit()
            return
        db.execute(
            text(
                f"""
                INSERT INTO {FTS_TABLE}
                    (session_id, user_id, title, messages, summary, tags)
                VALUES
                    (:session_id, :user_id, :title, :messages, :summary, :tags)
                """
            ),
            doc,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "FTS upsert failed",
            extra={"session_id": sid, "error": str(exc)},
        )
    finally:
        if owns_db:
            db.close()


def delete_session_fts(session_id: str, db: DbSession | None = None) -> None:
    ensure_session_fts()
    if not fts5_available():
        return
    sid = (session_id or "").strip()
    if not sid:
        return
    owns_db = db is None
    db = db or SessionLocal()
    try:
        db.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE session_id = :sid"),
            {"sid": sid},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "FTS delete failed",
            extra={"session_id": sid, "error": str(exc)},
        )
    finally:
        if owns_db:
            db.close()


def rebuild_all_session_fts() -> int:
    """Full reindex of all analysis_sessions. Returns document count."""
    ensure_session_fts()
    if not fts5_available():
        return 0
    db = SessionLocal()
    try:
        db.execute(text(f"DELETE FROM {FTS_TABLE}"))
        ids = [
            r[0]
            for r in db.execute(
                text("SELECT session_id FROM analysis_sessions")
            ).fetchall()
        ]
        db.commit()
        count = 0
        for sid in ids:
            upsert_session_fts(sid)
            count += 1
        logger.info("FTS full rebuild complete", extra={"count": count})
        return count
    finally:
        db.close()


def _highlight_fallback(text_value: str, tokens: list[str], max_len: int = 180) -> str:
    """Simple mark wrapping when FTS highlight is unavailable."""
    if not text_value:
        return ""
    body = text_value
    for tok in tokens:
        if not tok:
            continue
        pattern = re.compile(re.escape(tok), re.IGNORECASE)
        body = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", body)
    if len(body) > max_len:
        # Prefer a window around first mark
        idx = body.lower().find("<mark>")
        if idx < 0:
            return body[: max_len - 1] + "…"
        start = max(0, idx - 40)
        snippet = body[start : start + max_len]
        if start > 0:
            snippet = "…" + snippet
        if start + max_len < len(body):
            snippet = snippet + "…"
        return snippet
    return body


def search_sessions_fts(
    q: str,
    *,
    user_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_archived: bool = False,
    include_deleted: bool = False,
) -> dict[str, Any]:
    """
    Ranked FTS search across title, messages, summary, and tags.

    Returns:
      {
        query, match_query, total, limit, offset, engine,
        items: [{ session_id, title, rank, score, highlights, ...summary fields }]
      }
    """
    ensure_session_fts()
    limit = max(1, min(int(limit or 20), 100))
    offset = max(0, int(offset or 0))
    query = (q or "").strip()
    if not query:
        return {
            "query": "",
            "match_query": "",
            "total": 0,
            "limit": limit,
            "offset": offset,
            "engine": "none",
            "items": [],
        }

    if fts5_available():
        return _search_fts5(
            query,
            user_id=user_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )
    return _search_like_fallback(
        query,
        user_id=user_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        include_deleted=include_deleted,
    )


def _search_fts5(
    query: str,
    *,
    user_id: str | None,
    limit: int,
    offset: int,
    include_archived: bool,
    include_deleted: bool,
) -> dict[str, Any]:
    match_q = build_match_query(query)
    if not match_q:
        return {
            "query": query,
            "match_query": "",
            "total": 0,
            "limit": limit,
            "offset": offset,
            "engine": "fts5",
            "items": [],
        }

    w_title, w_msg, w_sum, w_tags = _BM25_WEIGHTS
    # bm25: more negative = better; we expose score = -bm25 for "higher is better"
    sql = f"""
        SELECT
            f.session_id AS session_id,
            f.user_id AS user_id,
            f.title AS title,
            f.messages AS messages,
            f.summary AS summary,
            f.tags AS tags,
            bm25({FTS_TABLE}, :w_title, :w_msg, :w_sum, :w_tags) AS rank,
            highlight({FTS_TABLE}, 2, '<mark>', '</mark>') AS title_hl,
            snippet({FTS_TABLE}, 3, '<mark>', '</mark>', '…', 32) AS messages_hl,
            highlight({FTS_TABLE}, 4, '<mark>', '</mark>') AS summary_hl,
            highlight({FTS_TABLE}, 5, '<mark>', '</mark>') AS tags_hl
        FROM {FTS_TABLE} AS f
        WHERE {FTS_TABLE} MATCH :match_q
    """
    params: dict[str, Any] = {
        "match_q": match_q,
        "w_title": w_title,
        "w_msg": w_msg,
        "w_sum": w_sum,
        "w_tags": w_tags,
    }
    if user_id:
        sql += " AND f.user_id = :user_id"
        params["user_id"] = user_id

    sql += " ORDER BY rank ASC"

    db = SessionLocal()
    try:
        try:
            rows = db.execute(text(sql), params).mappings().all()
        except Exception as exc:
            # Common when index empty / corrupt — rebuild once
            logger.warning(
                "FTS query failed; attempting rebuild",
                extra={"error": str(exc)},
            )
            db.rollback()
            rebuild_all_session_fts()
            rows = db.execute(text(sql), params).mappings().all()

        # Join analysis_sessions for status filters + metadata
        items: list[dict[str, Any]] = []
        for row in rows:
            sid = row["session_id"]
            meta = db.execute(
                text(
                    """
                    SELECT session_id, title, status, favorite, archived, deleted,
                           pinned, dataset_topic, dataset_name, message_count,
                           updated_at, last_activity_at, last_query, tags_json
                    FROM analysis_sessions
                    WHERE session_id = :sid
                    """
                ),
                {"sid": sid},
            ).mappings().first()
            if meta is None:
                continue
            if not include_deleted and meta.get("deleted"):
                continue
            if not include_archived and meta.get("archived"):
                continue

            bm25_rank = float(row["rank"] or 0.0)
            score = round(-bm25_rank, 6)  # higher is better
            highlights = {
                "title": row.get("title_hl") or meta.get("title") or "",
                "messages": row.get("messages_hl") or "",
                "summary": row.get("summary_hl") or "",
                "tags": row.get("tags_hl") or "",
            }
            # Which fields matched (contain <mark>)
            matched_fields = [
                name for name, val in highlights.items() if val and "<mark>" in val
            ]

            items.append(
                {
                    "session_id": sid,
                    "title": meta.get("title") or row.get("title") or "",
                    "rank": bm25_rank,
                    "score": score,
                    "matched_fields": matched_fields,
                    "highlights": highlights,
                    "snippet": (
                        highlights["messages"]
                        or highlights["summary"]
                        or highlights["title"]
                        or highlights["tags"]
                    ),
                    "status": meta.get("status") or "active",
                    "favorite": bool(meta.get("favorite")),
                    "archived": bool(meta.get("archived")),
                    "deleted": bool(meta.get("deleted")),
                    "pinned": bool(meta.get("pinned")),
                    "dataset_topic": meta.get("dataset_topic"),
                    "dataset_name": meta.get("dataset_name"),
                    "message_count": int(meta.get("message_count") or 0),
                    "updated_at": meta.get("updated_at"),
                    "last_activity_at": meta.get("last_activity_at"),
                    "last_query": meta.get("last_query"),
                    "tags": _parse_tags(meta.get("tags_json")),
                }
            )

        total = len(items)
        page = items[offset : offset + limit]
        return sanitize_for_json(
            {
                "query": query,
                "match_query": match_q,
                "total": total,
                "limit": limit,
                "offset": offset,
                "engine": "fts5",
                "items": page,
            }
        )
    finally:
        db.close()


def _parse_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str):
        try:
            import json

            data = json.loads(raw)
            if isinstance(data, list):
                return [str(t) for t in data]
        except Exception:
            return [raw] if raw else []
    return []


def _search_like_fallback(
    query: str,
    *,
    user_id: str | None,
    limit: int,
    offset: int,
    include_archived: bool,
    include_deleted: bool,
) -> dict[str, Any]:
    """LIKE-based fallback when FTS5 is unavailable."""
    tokens = _TOKEN_RE.findall(query.lower()) or [query.lower()]
    db = SessionLocal()
    try:
        sql = """
            SELECT s.session_id, s.title, s.status, s.favorite, s.archived,
                   s.deleted, s.pinned, s.dataset_topic, s.dataset_name,
                   s.message_count, s.updated_at, s.last_activity_at,
                   s.last_query, s.last_insight, s.tags_json
            FROM analysis_sessions s
            WHERE 1=1
        """
        params: dict[str, Any] = {}
        if user_id:
            sql += " AND s.user_id = :user_id"
            params["user_id"] = user_id
        if not include_deleted:
            sql += " AND (s.deleted = 0 OR s.deleted IS NULL)"
        if not include_archived:
            sql += " AND (s.archived = 0 OR s.archived IS NULL)"

        sessions = db.execute(text(sql), params).mappings().all()
        scored: list[dict[str, Any]] = []
        for s in sessions:
            sid = s["session_id"]
            msgs = _messages_blob(db, sid)
            title = s.get("title") or ""
            summary = (s.get("last_insight") or "") + " " + (s.get("last_query") or "")
            tags = _tags_text(_parse_tags(s.get("tags_json")))
            blob = f"{title}\n{msgs}\n{summary}\n{tags}".lower()
            hits = sum(1 for t in tokens if t in blob)
            if hits == 0:
                continue
            # Field weights for crude ranking
            score = 0.0
            matched: list[str] = []
            for t in tokens:
                if t in title.lower():
                    score += 10
                    matched.append("title")
                if t in msgs.lower():
                    score += 1
                    matched.append("messages")
                if t in summary.lower():
                    score += 5
                    matched.append("summary")
                if t in tags.lower():
                    score += 3
                    matched.append("tags")
            matched_fields = sorted(set(matched))
            highlights = {
                "title": _highlight_fallback(title, tokens),
                "messages": _highlight_fallback(msgs, tokens),
                "summary": _highlight_fallback(summary, tokens),
                "tags": _highlight_fallback(tags, tokens),
            }
            scored.append(
                {
                    "session_id": sid,
                    "title": title,
                    "rank": -score,
                    "score": score,
                    "matched_fields": matched_fields,
                    "highlights": highlights,
                    "snippet": (
                        highlights["messages"]
                        or highlights["summary"]
                        or highlights["title"]
                        or highlights["tags"]
                    ),
                    "status": s.get("status") or "active",
                    "favorite": bool(s.get("favorite")),
                    "archived": bool(s.get("archived")),
                    "deleted": bool(s.get("deleted")),
                    "pinned": bool(s.get("pinned")),
                    "dataset_topic": s.get("dataset_topic"),
                    "dataset_name": s.get("dataset_name"),
                    "message_count": int(s.get("message_count") or 0),
                    "updated_at": s.get("updated_at"),
                    "last_activity_at": s.get("last_activity_at"),
                    "last_query": s.get("last_query"),
                    "tags": _parse_tags(s.get("tags_json")),
                }
            )

        scored.sort(key=lambda x: (-x["score"], x["title"] or ""))
        total = len(scored)
        page = scored[offset : offset + limit]
        return sanitize_for_json(
            {
                "query": query,
                "match_query": " ".join(tokens),
                "total": total,
                "limit": limit,
                "offset": offset,
                "engine": "like",
                "items": page,
            }
        )
    finally:
        db.close()
