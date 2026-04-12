from sqlalchemy import create_engine, Column, String, JSON, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///memory.db"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class SessionMemory(Base):
    __tablename__ = "session_memory"

    session_id = Column(String, primary_key=True)
    dataset_path = Column(String)
    dataset_url = Column(String)
    last_column = Column(String)
    last_query = Column(Text)
    last_chart_type = Column(String)
    eda_summary = Column(JSON)
    last_insight = Column(Text)
    last_columns = Column(JSON)


Base.metadata.create_all(engine)

def get_session(session_id):

    db = SessionLocal()

    session = db.query(SessionMemory).filter(
        SessionMemory.session_id == session_id
    ).first()

    db.close()

    return session

def save_session(session_id, dataset_path=None, dataset_url=None,
                 last_column=None, last_query=None, last_chart_type=None,
                 eda_summary=None, last_insight=None, last_columns=None):

    db = SessionLocal()

    session = db.query(SessionMemory).filter(
        SessionMemory.session_id == session_id
    ).first()

    if not session:

        session = SessionMemory(
            session_id=session_id,
            dataset_path=dataset_path,
            dataset_url=dataset_url,
            last_column=last_column,
            last_query=last_query,
            last_chart_type=last_chart_type,
            eda_summary=eda_summary,
            last_insight=last_insight,
            last_columns=last_columns
        )

        db.add(session)

    else:

        if dataset_path:
            session.dataset_path = dataset_path

        if dataset_url:
            session.dataset_url = dataset_url

        if last_column:
            session.last_column = last_column

        if last_query:
            session.last_query = last_query

        if last_chart_type:
            session.last_chart_type = last_chart_type

        if eda_summary is not None:
            session.eda_summary = eda_summary

        if last_insight:
            session.last_insight = last_insight

        if last_columns:
            session.last_columns = last_columns

    db.commit()
    db.close()
