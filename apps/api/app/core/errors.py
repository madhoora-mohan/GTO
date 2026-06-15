# WHAT: Defines the AppError exception and the handlers that turn any
#       non-2xx response — AppError, validation errors, or a plain
#       HTTPException raised by Phase 2 code — into the same
#       {"error": ..., "message": ...} JSON shape.
# WHY:  The spec's ApiError schema is {error, message}. Routers raise
#       AppError for "expected" failures (404, 401, etc). FastAPI's own
#       RequestValidationError and any HTTPException from Phase 2 code
#       (auth_service, file_service) use different shapes by default —
#       these handlers normalize all of them to ApiError.

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Raised by route handlers for expected, "this status code on purpose"
    failures — e.g. AppError(404, "not_found", "Kanji '食' not found")."""

    def __init__(self, status: int, error: str, message: str):
        self.status = status
        self.error = error
        self.message = message


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        status_code=exc.status,
        content={"error": exc.error, "message": exc.message},
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": str(exc.errors())},
    )


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    # slowapi's built-in handler returns {"error": "Rate limit exceeded: ..."}
    # with no `message` field — normalize to the same ApiError shape as
    # every other error response.
    assert isinstance(exc, RateLimitExceeded)
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "message": str(exc.detail)},
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Phase 2 code (auth_service, file_service, deps/auth) raises plain
    # HTTPException with a `detail` string — normalize that to the same
    # {error, message} shape rather than FastAPI's default {"detail": ...}.
    assert isinstance(exc, StarletteHTTPException)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "message": str(exc.detail)},
    )
