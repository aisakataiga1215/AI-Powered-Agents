"""Time helpers.

Centralizes timestamp formatting so all schemas/services emit
ISO-8601 UTC strings consistently.
"""

from datetime import datetime


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.utcnow().isoformat()
