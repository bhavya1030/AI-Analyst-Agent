from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///memory.db"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class SessionMemory(Base):
    __tablename__ = "session_memory"

    session_id = Column(String, primary_key=True)
    dataset_path = Column(String)
    last_column = Column(String)
    last_columns = Column(String)


Base.metadata.create_all(engine)

def get_session(session_id):

    db = SessionLocal()

    session = db.query(SessionMemory).filter(
        SessionMemory.session_id == session_id
    ).first()

    db.close()

    return session

def save_session(session_id, dataset_path=None,
                 last_column=None, last_columns=None):

    db = SessionLocal()

    session = db.query(SessionMemory).filter(
        SessionMemory.session_id == session_id
    ).first()

    if not session:

        session = SessionMemory(
            session_id=session_id,
            dataset_path=dataset_path,
            last_column=last_column,
            last_columns=last_columns
        )

        db.add(session)

    else:

        if dataset_path:
            session.dataset_path = dataset_path

        if last_column:
            session.last_column = last_column

        if last_columns:
            session.last_columns = last_columns

    db.commit()
    db.close()