"""Database session and engine setup.

Uses SQLAlchemy 2.0 sync engine. The MVP target is SQLite, but the
engine kwargs auto-adapt when ``DATABASE_URL`` points to PostgreSQL.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import NoSuchTableError
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


def _add_column_if_missing(table_name: str, column_name: str, ddl: str) -> None:
    with engine.connect() as conn:
        try:
            existing_columns = {column["name"] for column in inspect(conn).get_columns(table_name)}
        except NoSuchTableError:
            return
        if column_name in existing_columns:
            return
        conn.execute(text(ddl))
        conn.commit()


def _apply_migrations() -> None:
    _add_column_if_missing(
        "projects",
        "data_mode",
        "ALTER TABLE projects ADD COLUMN data_mode TEXT DEFAULT 'demo'"
    )
    _add_column_if_missing(
        "sources",
        "data_source",
        "ALTER TABLE sources ADD COLUMN data_source TEXT DEFAULT 'demo'"
    )
    _add_column_if_missing(
        "projects",
        "industry_type",
        "ALTER TABLE projects ADD COLUMN industry_type TEXT DEFAULT 'general'"
    )
    _add_column_if_missing(
        "projects",
        "analysis_purpose",
        "ALTER TABLE projects ADD COLUMN analysis_purpose TEXT DEFAULT 'general'"
    )
    _add_column_if_missing(
        "projects",
        "custom_dimensions",
        "ALTER TABLE projects ADD COLUMN custom_dimensions TEXT DEFAULT '[]'"
    )
    _add_column_if_missing(
        "projects",
        "research_inputs",
        "ALTER TABLE projects ADD COLUMN research_inputs TEXT DEFAULT '[]'"
    )
    _add_column_if_missing(
        "competitors",
        "role",
        "ALTER TABLE competitors ADD COLUMN role TEXT DEFAULT 'direct_competitor'"
    )
    _add_column_if_missing(
        "competitors",
        "extra_urls",
        "ALTER TABLE competitors ADD COLUMN extra_urls TEXT DEFAULT '[]'"
    )


_apply_migrations()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it when the request ends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
