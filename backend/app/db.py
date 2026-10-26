"""Database engine, session factory, declarative Base and idempotent schema init."""

import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

# Arbitrary constant key for the schema-init advisory lock.
_INIT_LOCK_KEY = 7_204_118_351


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_pk():
    """UUID primary key column (default uuid4)."""
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_col():
    return mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


def updated_at_col():
    return mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request; rollback on error, always close."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_jobs_search_vector ON jobs USING gin (search_vector)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_title_trgm ON jobs USING gin (title gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_skills_name_trgm ON skills USING gin (name gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_companies_name_trgm ON companies USING gin (name gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_required_skills_gin ON jobs USING gin (required_skills)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_preferred_skills_gin ON jobs USING gin (preferred_skills)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_locations_gin ON jobs USING gin (locations)",
)


def init_db() -> None:
    """Create extensions, tables and search indexes. Idempotent and safe under concurrent starts."""
    from app import models  # noqa: F401  (registers every model on Base.metadata)

    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _INIT_LOCK_KEY})
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.commit()
            Base.metadata.create_all(bind=conn)
            conn.commit()
            for stmt in _INDEX_STATEMENTS:
                conn.execute(text(stmt))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _INIT_LOCK_KEY})
            conn.commit()
    logger.info("Database schema initialised")


def dispose_engine() -> None:
    engine.dispose()
