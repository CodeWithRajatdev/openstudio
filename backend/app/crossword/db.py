"""SQLAlchemy 2.x database setup & Alembic migrations (SQLite default, PostgreSQL-compatible)."""
from __future__ import annotations

from pathlib import Path
from typing import Generator

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        raw_path = database_url.removeprefix("sqlite:///")
        raw_path = raw_path.split("?", 1)[0]
        if raw_path and raw_path != ":memory:":
            Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str) -> Engine:
    _ensure_sqlite_dir(database_url)
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    return eng


_settings = get_settings()
engine = create_db_engine(_settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def run_migrations(target_engine: Engine | None = None) -> None:
    """Run Alembic migrations up to head on the given engine (works on fresh & legacy DBs)."""
    from . import models  # noqa: F401  ensure all models are registered on Base

    eng = target_engine or engine
    alembic_ini = BACKEND_DIR / "alembic.ini"
    alembic_dir = BACKEND_DIR / "alembic"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_dir))
    cfg.attributes["skip_logging_config"] = True

    with eng.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


def init_db(target_engine: Engine | None = None) -> None:
    run_migrations(target_engine=target_engine)


def get_session_factory():
    return SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
