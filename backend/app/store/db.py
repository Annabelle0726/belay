"""SQLAlchemy engine + session.

SQLite is the zero-config durable DEFAULT (`settings.database_url`); set
`DATABASE_URL` to a Postgres DSN to opt in to Postgres behind the same interface.
The DSN is sourced from config (env-driven) so the store posture is explicit and
testable; no code path requires Postgres. The models are portable as-is."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..config import settings
from .models import Base

# Re-exported for tests/tools; the source of truth is settings.database_url.
DATABASE_URL = settings.database_url

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
