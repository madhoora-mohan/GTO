# WHAT: The `get_current_user` FastAPI dependency — figures out "who is
#       making this request?" from the Authorization header.
# WHY:  Almost every protected route (and all of Phase 3's content routes,
#       e.g. the kanji mnemonic PATCH) needs to know the current user. Rather
#       than every route handler re-implementing "read the header, decode the
#       JWT, load the user, handle errors," they just declare
#       `user: User = Depends(get_current_user)` and FastAPI runs this once
#       per request, wiring the result straight into the handler's arguments.
#
# Note this only ever looks at the *access* token (never the refresh-token
# cookie) and never touches the `refresh_tokens` table — verifying a JWT
# signature is a pure crypto check, so this stays fast and DB-free on every
# request. Refresh-token DB lookups only happen in the /auth/refresh flow
# (services/auth_service.py).

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decode_token
from app.models.user import User

# HTTPBearer is FastAPI's helper for the "Authorization: Bearer <token>"
# header convention. `auto_error=True` (the default) makes it return a 401
# automatically if the header is missing or malformed — one less case for us
# to handle by hand.
_bearer_scheme = HTTPBearer()

# A single shared 401 — used for every "this token/user isn't valid" case.
# We deliberately give the *same* generic message in every branch (missing
# token, bad signature, expired, wrong type, user no longer exists) so a
# client can't use error-message differences to probe which part failed.
_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the User making this request from their Bearer access token.

    Raises 401 if the token is missing, malformed, expired, signed with the
    wrong secret, is a refresh token (not an access token), or names a user
    that no longer exists.
    """
    token = credentials.credentials

    try:
        payload = decode_token(token, expected_type="access")
    except jwt.PyJWTError:
        # Covers: bad signature, expired (`exp` in the past), malformed token,
        # and our own "wrong token type" check inside decode_token.
        raise _UNAUTHORIZED

    # The "sub" claim is the user's id, stored as a string because JWT claims
    # must be JSON-serialisable (UUID objects aren't). Convert it back here;
    # if it's not a valid UUID, the token was never one we issued.
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise _UNAUTHORIZED

    user = await db.get(User, user_id)
    if user is None:
        # The token is cryptographically valid, but the user it points to is
        # gone (e.g. account deleted after the token was issued).
        raise _UNAUTHORIZED

    return user
