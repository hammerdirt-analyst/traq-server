"""SQLAlchemy database bootstrap for the TRAQ server.

Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

This module defines the engine/session boundary for the PostgreSQL migration.
It does not change runtime behavior by itself. Existing endpoints can adopt this
layer incrementally while filesystem-backed metadata is retired.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    """Declarative base for all TRAQ ORM models."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_database(settings: Settings) -> None:
    """Initialize the process-wide SQLAlchemy engine and session factory.

    The server is expected to call this once during startup. The engine is kept
    module-local so existing code can migrate to database-backed services
    without threading a session factory through every helper immediately.
    """

    global _engine, _SessionLocal
    if _engine is not None and _SessionLocal is not None:
        return
    _engine = create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def get_engine() -> Engine:
    """Return the initialized SQLAlchemy engine."""

    if _engine is None:
        raise RuntimeError("Database engine has not been initialized")
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a database session with commit/rollback handling."""

    if _SessionLocal is None:
        raise RuntimeError("Database session factory has not been initialized")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_schema() -> None:
    """Create all mapped tables for local bootstrap/testing.

    Production schema changes should go through Alembic migrations. This helper
    exists so the initial database layer can be validated before migration files
    are introduced.
    """

    from . import db_models  # noqa: F401  Ensures model metadata is registered.

    Base.metadata.create_all(bind=get_engine())
