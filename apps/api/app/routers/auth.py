# WHAT: Defines the `/auth/*` HTTP routes — register, login, refresh, logout.
# WHY:  FastAPI organizes endpoints into "routers" (groups of related routes)
#       that get mounted onto the main app in main.py. Keeping auth routes in
#       their own file/router keeps main.py small and makes it easy to add
#       more route groups later (e.g. routers/kanji.py in Phase 3) without
#       main.py turning into a dumping ground for every endpoint.
#
# These handlers stay deliberately thin: parse the request (FastAPI does this
# via the generated Pydantic schemas), delegate the real work to
# auth_service.py, then shape the HTTP response (status code, cookie, body).
# All the business rules — reuse detection, dead-token cleanup, hashing,
# soft-revocation — live in the service layer where they're easier to test
# and reason about without HTTP concerns mixed in.

from typing import Literal, TypedDict

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.limiter import limiter
from app.schemas.generated import AuthResponse, LoginInput, RefreshResponse, RegisterInput
from app.schemas.generated import User as UserSchema
from app.services import auth_service

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Refresh-token cookie settings
# ─────────────────────────────────────────────────────────────────────────────
#
# These exact attributes must be used every time we set OR clear the cookie —
# browsers identify a cookie by (name, domain, path), and `delete_cookie` only
# actually removes it if the attributes match how it was set. Centralising
# them here means register/login/refresh (which set it) and logout (which
# clears it) can't drift out of sync.
#
#   httponly=True   -> JavaScript can never read this cookie (defends against
#                       XSS stealing the refresh token)
#   secure=True     -> only sent over HTTPS (Render gives us HTTPS in prod;
#                       see phase-2.md's note about a dev toggle if you ever
#                       need to test the cookie flow over plain http://localhost)
#   samesite="lax"  -> not sent on cross-site subrequests/iframes, but IS sent
#                       when the user navigates here directly — blocks CSRF
#                       without breaking normal top-level navigation
#   max_age         -> 30 days, matching the refresh token's own JWT `exp`
_REFRESH_COOKIE_NAME = "refresh_token"
class _RefreshCookieKwargs(TypedDict):
    httponly: bool
    secure: bool
    samesite: Literal["lax", "strict", "none"]


_REFRESH_COOKIE_KWARGS: _RefreshCookieKwargs = {
    "httponly": True,
    "secure": True,
    "samesite": "lax",
}
_REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days, in seconds


def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=_REFRESH_COOKIE_MAX_AGE,
        **_REFRESH_COOKIE_KWARGS,
    )


def _clear_refresh_cookie(response: Response) -> None:
    # `delete_cookie` needs the same httponly/secure/samesite attributes used
    # when setting it, or the browser won't recognise it as the same cookie
    # and won't actually delete it.
    response.delete_cookie(key=_REFRESH_COOKIE_NAME, **_REFRESH_COOKIE_KWARGS)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterInput,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create an account, log the user in immediately (issue both tokens)."""
    user = await auth_service.register_user(db, body.email, body.password)
    access_token, refresh_token = await auth_service.issue_token_pair(db, user)
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(access_token=access_token, user=UserSchema.model_validate(user, from_attributes=True))


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginInput,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Verify credentials, sweep dead refresh-token rows, then log in."""
    user = await auth_service.authenticate_user(db, body.email, body.password)

    # Per phase-2.md's "dead token cleanup" decision: this is the ONE place
    # we prune revoked/expired refresh_token rows — deliberately on login
    # (≈ once per 30 days per user) rather than on every refresh (every 15
    # minutes) or via a separate cron job.
    await auth_service.cleanup_dead_refresh_tokens(db, user.id)

    access_token, refresh_token = await auth_service.issue_token_pair(db, user)
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(access_token=access_token, user=UserSchema.model_validate(user, from_attributes=True))


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
) -> RefreshResponse:
    """Rotate the refresh-token cookie and issue a fresh access token.

    `auth_service.rotate_refresh_token` does the heavy lifting: verifying the
    JWT, detecting reuse (and nuking all sessions if found), soft-revoking
    the old row, and issuing a brand new pair. We just need to make sure the
    *new* cookie ends up on the response — including in the reuse-detected
    case, where the service raises 401 but we should still clear whatever
    cookie the client sent us (it's now useless).
    """
    if refresh_token is None:
        _clear_refresh_cookie(response)
        raise auth_service.INVALID_REFRESH_TOKEN

    try:
        new_access_token, new_refresh_token = await auth_service.rotate_refresh_token(db, refresh_token)
    except Exception:
        # Whatever went wrong (bad signature, expired, unknown, reuse — see
        # auth_service for the full breakdown), the cookie the client sent is
        # no longer good for anything. Clear it so the browser stops resending
        # a dead token on every request.
        _clear_refresh_cookie(response)
        raise

    _set_refresh_cookie(response, new_refresh_token)
    return RefreshResponse(access_token=new_access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE_NAME),
) -> Response:
    """Revoke the current refresh token (if any) and clear the cookie.

    Always succeeds with 204 — even if there's no cookie or it doesn't match
    a live row. From the client's point of view, "log me out" should always
    end in "you are logged out," regardless of whether there was anything to
    actually revoke server-side.
    """
    if refresh_token is not None:
        await auth_service.revoke_refresh_token(db, refresh_token)

    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
