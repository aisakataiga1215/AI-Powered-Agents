"""FastAPI dependency wiring."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_db


def get_session() -> Generator[Session, None, None]:
    """Yield a database session for route handlers.

    This is a thin alias around :func:`app.db.session.get_db` so route
    modules can depend on the API layer rather than the db package.
    """
    yield from get_db()
