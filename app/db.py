from sqlmodel import SQLModel, create_engine, Session
from pathlib import Path

DB_PATH = Path("weather.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)
