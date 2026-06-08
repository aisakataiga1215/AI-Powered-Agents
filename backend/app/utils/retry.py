"""Retry utility.

Light wrapper around :func:`time.sleep` based retry that the agents and
services can use without pulling in a heavier dependency for the MVP.
"""

import time
from collections.abc import Callable
from typing import TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    max_attempts: int = 3,
    backoff_seconds: float = 0.5,
) -> T:
    """Run ``fn`` up to ``max_attempts`` times with linear backoff.

    Re-raises the final exception if every attempt fails.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - intentional broad catch
            last_exc = exc
            logger.warning(
                "with_retry attempt %d/%d failed: %s",
                attempt,
                max_attempts,
                exc,
            )
            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)
    assert last_exc is not None  # for type checkers
    raise last_exc
