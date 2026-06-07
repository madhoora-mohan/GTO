# WHAT: The DB-touching half of auth — creating users, checking credentials,
#       and issuing/rotating/revoking refresh-token rows. Pairs with
#       core/security.py (the crypto-only half: hashing, JWT encode/decode).
# WHY:  routers/auth.py should stay thin — just "parse the request, call a
#       service function, shape the response." All the actual business rules
#       (reuse detection, dead-token cleanup, soft-revocation) live here where
#       they can be tested and reasoned about independently of HTTP concerns.
#
# Functions here raise `HTTPException` directly (rather than custom exception
# types the router would have to translate) — there's exactly one caller
# (routers/auth.py) and exactly one thing it would do with a custom exception:
# turn it into an HTTPException. Skipping that indirection keeps this small.

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User

# A generic 401 for "email or password is wrong." Reused by both register
# (email-taken case maps to a 400, not this) and login, and deliberately
# vague — telling an attacker "that email isn't registered" vs "wrong
# password" leaks which emails have accounts (a user-enumeration bug).
_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
)

# A generic 401 for anything wrong with the refresh-token cookie itself
# (missing, malformed, expired, unknown, or reused). Same reasoning as above:
# don't give an attacker probing this endpoint any signal about *why* a
# particular cookie failed.
INVALID_REFRESH_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired refresh token",
)


def _hash_token(raw_token: str) -> str:
    """Hash a raw refresh-token JWT for storage/lookup.

    We store SHA-256 hex digests (not the raw JWT) in `refresh_tokens.token_hash`
    — per Task 0.4's decision, the row must be *kept* (not deleted) on use so
    that a replayed token can be recognised as reuse. Storing only a hash means
    that even if the `refresh_tokens` table leaked, the tokens themselves
    couldn't be reconstructed from it (the same property bcrypt gives
    passwords — except here we don't need bcrypt's slowness, since the JWT
    itself is already a long random-looking secret, not a guessable password).
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Registration / login
# ─────────────────────────────────────────────────────────────────────────────


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    """Create a new user account.

    Raises 400 if the email is already registered. (Unlike the login 401,
    this one *can* be specific — at the registration step there's no
    meaningful "which field was wrong" ambiguity to protect; the user is
    actively telling us their email, and a generic error here would just be
    a worse signup experience for no security benefit.)
    """
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists",
        )

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """Verify email+password, returning the matching User.

    Raises a generic 401 (`_INVALID_CREDENTIALS`) if the email isn't
    registered OR the password doesn't match — same response either way, so
    a failed lookup and a failed password check are indistinguishable to the
    caller.
    """
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        raise _INVALID_CREDENTIALS
    return user


async def cleanup_dead_refresh_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Delete this user's revoked-or-expired refresh-token rows.

    Per phase-2.md's "dead token cleanup" decision: this runs once, at the
    start of a successful login — not on every refresh (which would be
    ~2,880x more frequent for the same result) and not via a cron job (login
    rate-limiting in Phase 3 bounds how often this query can run; a handful
    of stale rows from users who never log back in isn't worth extra
    infrastructure to chase down).
    """
    await db.execute(
        delete(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(
            or_(
                RefreshToken.revoked_at.is_not(None),
                RefreshToken.expires_at < _utcnow(),
            )
        )
    )
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Token issuance
# ─────────────────────────────────────────────────────────────────────────────


async def issue_token_pair(db: AsyncSession, user: User) -> tuple[str, str]:
    """Issue a fresh access token + refresh token for `user`.

    Used by both register and login (they end identically once you have a
    User object) and by the rotation step of /auth/refresh.

    The access token is handed back as-is (the route puts it in the response
    body). The refresh token is recorded in the DB *hashed* — only the raw
    JWT, which never touches our database, goes to the client (as an
    HttpOnly cookie, set by the route).

    Returns (access_token_jwt, refresh_token_jwt).
    """
    access_token = create_access_token(user.id)
    refresh_token, _jti, expires_at = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(refresh_token),
            expires_at=expires_at,
        )
    )
    await db.commit()

    return access_token, refresh_token


# ─────────────────────────────────────────────────────────────────────────────
# Refresh rotation (with reuse detection) and revocation
# ─────────────────────────────────────────────────────────────────────────────


async def rotate_refresh_token(db: AsyncSession, raw_refresh_token: str) -> tuple[str, str]:
    """Validate, rotate, and replace a refresh token — the heart of /auth/refresh.

    Steps (matching phase-2.md's Task 3 endpoint table exactly):
      1. Verify the JWT itself (signature + exp + correct `type`). A failure
         here means the cookie is garbage/expired — generic 401.
      2. Look up its hashed row. Missing means it's not a token we issued
         (or it was already cleaned up post-expiry) — generic 401.
      3. **If the row is already revoked, this exact token has been used
         before.** That's only possible if it was stolen and replayed (the
         legitimate client would have the *new* rotated token by now, not
         this one) — so we revoke EVERY refresh token this user has, forcing
         all sessions (legitimate and attacker's alike) to re-authenticate.
         This is the "theft detection" the spec calls for.
      4. Otherwise: this is a legitimate, single-use refresh. Revoke this row
         (so it can't be replayed) and issue a brand new pair.

    Returns (new_access_token_jwt, new_refresh_token_jwt). Raises 401 on any
    failure — the route clears the cookie either way.
    """
    try:
        payload = decode_token(raw_refresh_token, expected_type="refresh")
    except Exception:
        raise INVALID_REFRESH_TOKEN

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise INVALID_REFRESH_TOKEN

    token_hash = _hash_token(raw_refresh_token)
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if row is None or row.expires_at < _utcnow():
        raise INVALID_REFRESH_TOKEN

    if row.revoked_at is not None:
        # Reuse detected — nuke every session this user has.
        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id == row.user_id)
        )
        await db.commit()
        raise INVALID_REFRESH_TOKEN

    user = await db.get(User, user_id)
    if user is None:
        raise INVALID_REFRESH_TOKEN

    # Soft-revoke the old row (set revoked_at) rather than deleting it — per
    # Task 0.4, keeping the row is what makes the reuse-detection above
    # possible: a replayed *deleted* token would be indistinguishable from
    # random garbage, and we'd have no way to know it was reuse vs. just a
    # bad guess.
    row.revoked_at = _utcnow()
    db.add(row)
    await db.commit()

    return await issue_token_pair(db, user)


async def revoke_refresh_token(db: AsyncSession, raw_refresh_token: str) -> None:
    """Soft-revoke the row matching this raw refresh token (logout).

    Deliberately silent about whether a matching row was found: logging out
    with an already-invalid/missing cookie should still look like a
    successful logout to the client (the end state — "no valid session" — is
    the same either way), and we don't want to leak info about which cookie
    values correspond to real tokens.
    """
    token_hash = _hash_token(raw_refresh_token)
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if row is not None and row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.add(row)
        await db.commit()
