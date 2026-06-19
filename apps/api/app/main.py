# WHAT: The FastAPI app's entry point / "factory" — the single place where
#       the `app` object is created and everything gets wired onto it:
#       middleware (CORS), routers (route groups like /auth/*), and the
#       /health endpoint.
# WHY:  Uvicorn needs one importable `app` object to serve (`app.main:app`),
#       and every piece of global setup (CORS rules, which routers exist,
#       startup checks, etc.) has to happen *somewhere* before requests are
#       handled. Centralizing it here means you can see the whole shape of
#       the API — what middleware runs, what route groups exist — in one file,
#       instead of hunting through the codebase for side-effecting imports.
#
# Run it locally with:
#   uv run uvicorn app.main:app --reload
# then open http://localhost:8000/docs for interactive API docs (Swagger UI).

import sentry_sdk
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    rate_limit_exceeded_handler,
    validation_error_handler,
)
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.routers import auth, components, files, kana, kanji, reading, sentences, vocab

configure_logging()

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.2,
        environment="production",
    )

app = FastAPI(title="GTO API", version="0.1.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# CORS = Cross-Origin Resource Sharing. By default, browsers block JavaScript
# on one origin (e.g. http://localhost:5173, our web app) from making requests
# to a different origin (e.g. http://localhost:8000, this API). This middleware
# tells the browser "these specific origins are allowed to talk to me."
#
# Two things matter here:
#   - `allow_origins` MUST be an explicit list of origins (no "*" wildcard).
#   - `allow_credentials=True` is required so the browser will send/receive
#     our HttpOnly refresh-token cookie cross-origin.
# These two cannot be combined with a wildcard — the browser spec forbids it,
# since "any site can send credentialed requests" would be a security hole.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the auth router under the /auth prefix, so its routes become
# /auth/register, /auth/login, /auth/refresh, /auth/logout. The "tags" group
# them together under an "auth" heading in the /docs Swagger UI.
app.include_router(auth.router, prefix="/auth", tags=["auth"])

# Mount the files router under the /files prefix, so its routes become
# /files/presign and /files/confirm — the presigned R2 upload flow.
app.include_router(files.router, prefix="/files", tags=["files"])

# Mount the kana router under the /kana prefix.
app.include_router(kana.router, prefix="/kana", tags=["kana"])

app.include_router(kanji.router, prefix="/kanji", tags=["kanji"])

app.include_router(vocab.router, prefix="/vocab", tags=["vocab"])

app.include_router(sentences.router, prefix="/sentences", tags=["sentences"])

app.include_router(components.router, prefix="/components", tags=["components"])

app.include_router(reading.router, prefix="/reading", tags=["reading"])


@app.get("/health")
def health():
    """Simple liveness check. Render polls this URL to know the service is up."""
    return {"status": "ok"}
