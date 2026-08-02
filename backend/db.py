from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import settings

# SQLite Reliability v2: allow multi-thread + durable concurrent reads after write
_connect_args: dict = {"check_same_thread": False}
if str(settings.DATABASE_URL).startswith("sqlite"):
    # timeout is the Python sqlite3 busy wait (seconds)
    _connect_args["timeout"] = 30.0

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)

Base = declarative_base()


@event.listens_for(engine, "connect")
def _sqlite_on_connect(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    """Apply per-connection durability pragmas (WAL, busy_timeout, FKs)."""
    if not str(settings.DATABASE_URL).startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def ensure_analysis_session_schema():
    """Create Phase-1 session tables (analysis_sessions, messages, artifacts)."""
    try:
        from backend.sessions.service import ensure_session_tables

        ensure_session_tables()
    except Exception:
        # Avoid import cycles / partial installs breaking legacy paths
        pass


ensure_analysis_session_schema()


def ensure_analysis_cache_schema():
    """Create Phase-2 durable AnalysisCache table."""
    try:
        from backend.cache.analysis_cache import ensure_analysis_cache_table

        ensure_analysis_cache_table()
    except Exception:
        pass


ensure_analysis_cache_schema()


def ensure_auth_users_schema():
    """Create Phase-8 users table + anonymous seed."""
    try:
        from backend.auth.service import ensure_auth_schema

        ensure_auth_schema()
    except Exception:
        pass


ensure_auth_users_schema()
