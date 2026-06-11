"""Custom application errors with HTTP status mapping.

The FastAPI exception handlers in :mod:`app.main` translate these into
structured JSON error responses.
"""


class AppError(Exception):
    """Base application error.

    Carries an HTTP status code so FastAPI can render a consistent
    structured error response.
    """

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            f"{resource} '{resource_id}' not found",
            status_code=404,
        )


class WorkflowError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status_code=500)


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status_code=409)
