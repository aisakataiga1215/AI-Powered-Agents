"""Database session and engine setup.

Uses SQLAlchemy 2.0 sync engine. The MVP target is SQLite, but the
engine kwargs auto-adapt when ``DATABASE_URL`` points to PostgreSQL.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_connect_args: dict = {}
if "sqlite" in settings.database_url:
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _add_column_if_missing(ddl: str) -> None:
    with engine.connect() as conn:
        try:
            conn.execute(text(ddl))
            conn.commit()
        except OperationalError as exc:
            if "duplicate column" in str(exc).lower():
                pass
            else:
                raise


def _apply_migrations() -> None:
    _add_column_if_missing(
        "ALTER TABLE projects ADD COLUMN data_mode TEXT DEFAULT 'demo'"
    )
    _add_column_if_missing(
        "ALTER TABLE sources ADD COLUMN data_source TEXT DEFAULT 'demo'"
    )
    _add_column_if_missing(
        "ALTER TABLE projects ADD COLUMN industry_type TEXT DEFAULT 'general'"
    )
    _add_column_if_missing(
        "ALTER TABLE projects ADD COLUMN analysis_purpose TEXT DEFAULT 'general'"
    )
    _add_column_if_missing(
        "ALTER TABLE projects ADD COLUMN custom_dimensions TEXT DEFAULT '[]'"
    )
    _add_column_if_missing(
        "ALTER TABLE competitors ADD COLUMN role TEXT DEFAULT 'direct_competitor'"
    )


_apply_migrations()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it when the request ends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
