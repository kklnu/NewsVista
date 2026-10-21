from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce ON DELETE CASCADE in SQLite
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    # prepare_threshold=None keeps psycopg compatible with Supabase's pooler.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        connect_args={"prepare_threshold": None, "connect_timeout": 15},
    )


class Database:
    def __init__(self, url: str):
        self.engine = make_engine(url)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self.SessionLocal()


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(settings.database_url)
    return _db


def set_db(db: Database) -> None:
    """Used by tests to point the app at an isolated database."""
    global _db
    _db = db
