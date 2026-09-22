"""Database engine and session management.

SQLite in development, PostgreSQL in production — same SQLModel code path.
`init_db()` creates tables only for fresh SQLite dev databases; production
schema changes go through Alembic migrations exclusively.
"""
import logging

from sqlalchemy import text
from sqlmodel import Session, create_engine

from .config import settings

logger = logging.getLogger(__name__)

is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    # SQLite needs the thread flag because FastAPI sync handlers can hop threads.
    connect_args={"check_same_thread": False} if is_sqlite else {},
    # Pooled engines (Postgres) should drop broken connections instead of
    # serving them — cheap insurance for managed-DB restarts.
    pool_pre_ping=not is_sqlite,
)


def init_db() -> None:
    """Create tables when running on a fresh SQLite dev database.

    On PostgreSQL this is a no-op unless the `observation` table is missing —
    the normal path is `alembic upgrade head` (see render.yaml deploy command).
    """
    if not is_sqlite:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT to_regclass('public.observation')")
            ).scalar()
        if exists:
            return
        logger.warning(
            "observation table missing on PostgreSQL — did you run alembic upgrade head?"
        )
    from sqlmodel import SQLModel

    import app.models as _models  # noqa: F401  (register table metadata)

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
