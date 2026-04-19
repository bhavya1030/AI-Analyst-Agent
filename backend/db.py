from sqlalchemy import JSON, Column, String, Text, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

Base = declarative_base()


class SessionMemory(Base):
    __tablename__ = "session_memory"

    session_id = Column(String, primary_key=True)
    dataset_path = Column(String)
    dataset_url = Column(String)
    last_column = Column(String)
    last_query = Column(Text)
    last_chart_type = Column(String)
    last_intent = Column(String)
    last_operation = Column(String)
    last_forecast_target = Column(String)
    eda_summary = Column(JSON)
    last_insight = Column(Text)
    last_columns = Column(JSON)
    dataset_topic = Column(String)


EXPECTED_COLUMNS = {
    "dataset_path": "VARCHAR",
    "dataset_url": "VARCHAR",
    "last_column": "VARCHAR",
    "last_query": "TEXT",
    "last_chart_type": "VARCHAR",
    "last_intent": "VARCHAR",
    "last_operation": "VARCHAR",
    "last_forecast_target": "VARCHAR",
    "eda_summary": "JSON",
    "last_insight": "TEXT",
    "last_columns": "JSON",
    "dataset_topic": "VARCHAR",
}


def ensure_session_memory_schema():
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        inspector = inspect(connection)

        if "session_memory" not in inspector.get_table_names():
            return

        existing_columns = {
            column["name"]
            for column in inspector.get_columns("session_memory")
        }

        for column_name, column_type in EXPECTED_COLUMNS.items():
            if column_name in existing_columns:
                continue

            connection.execute(
                text(
                    f"ALTER TABLE session_memory "
                    f"ADD COLUMN {column_name} {column_type}"
                )
            )


ensure_session_memory_schema()

_UNSET = object()


def get_session(session_id):

    db = SessionLocal()

    session = db.query(SessionMemory).filter(
        SessionMemory.session_id == session_id
    ).first()

    db.close()

    return session


def list_sessions():
    db = SessionLocal()
    session_ids = [session.session_id for session in db.query(SessionMemory.session_id).all()]
    db.close()
    return session_ids


def save_session(
    session_id,
    dataset_path=_UNSET,
    dataset_url=_UNSET,
    last_column=_UNSET,
    last_query=_UNSET,
    last_chart_type=_UNSET,
    last_intent=_UNSET,
    last_operation=_UNSET,
    last_forecast_target=_UNSET,
    eda_summary=_UNSET,
    last_insight=_UNSET,
    last_columns=_UNSET,
    dataset_topic=_UNSET,
):

    db = SessionLocal()

    session = db.query(SessionMemory).filter(
        SessionMemory.session_id == session_id
    ).first()

    if not session:

        session = SessionMemory(session_id=session_id)

        db.add(session)

    updates = {
        "dataset_path": dataset_path,
        "dataset_url": dataset_url,
        "last_column": last_column,
        "last_query": last_query,
        "last_chart_type": last_chart_type,
        "last_intent": last_intent,
        "last_operation": last_operation,
        "last_forecast_target": last_forecast_target,
        "eda_summary": eda_summary,
        "last_insight": last_insight,
        "last_columns": last_columns,
        "dataset_topic": dataset_topic,
    }

    for field_name, value in updates.items():
        if value is _UNSET:
            continue
        setattr(session, field_name, value)

    db.commit()
    db.close()
