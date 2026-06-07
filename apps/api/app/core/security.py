# WHAT: Low-level cryptographic helpers for auth — hashing/checking passwords,
#       and encoding/decoding the two kinds of JWTs (access + refresh).
# WHY:  These operations (bcrypt, JWT signing) are security-sensitive and
#       fiddly to get right (byte limits, expiry math, payload shape). Putting
#       them in one small, well-tested module means auth_service.py and
#       deps/auth.py can call simple functions like `create_access_token(...)`
#       without worrying about the crypto details — and if we ever need to
#       change algorithms or libraries, there's exactly one place to do it.
#
# This module deliberately does NOT touch the database — it's pure
# crypto/encoding logic. DB-touching token issue/rotate/revoke logic lives in
# services/auth_service.py.

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

# How long each token type is valid for. These come straight from the spec
# (phase-2.md Task 3): short-lived access tokens limit the damage if one
# leaks; long-lived refresh tokens let users stay logged in without
# re-entering their password every 15 minutes.
ACCESS_TOKEN_EXPIRE = timedelta(minutes=15)
REFRESH_TOKEN_EXPIRE = timedelta(days=30)

# JWTs are signed (not encrypted) — anyone can read the payload, but only
# someone with `jwt_secret` can produce a signature that verifies. HS256 is
# a symmetric algorithm: the same secret signs and verifies, which is fine
# here because only this API ever needs to check these tokens.
JWT_ALGORITHM = "HS256"


# ─────────────────────────────────────────────────────────────────────────────
# Password hashing
# ─────────────────────────────────────────────────────────────────────────────
#
# We NEVER store raw passwords. bcrypt takes a password, mixes in a random
# "salt", and runs many rounds of hashing — the result is a one-way string
# that's cheap to verify but extremely expensive to reverse/brute-force.
# `users.hashed_password` is `String(60)` because that's exactly the length
# of a bcrypt hash string.

# bcrypt has a quirk: it silently ignores any bytes beyond the 72nd byte of
# the input. Two different long passwords that share the same first 72 bytes
# would hash identically. `RegisterInput`/`LoginInput` already enforce an
# 8-character minimum (not a maximum), so in practice this only matters for
# unusually long passwords — but we guard against it explicitly rather than
# relying on bcrypt's silent truncation, since silent truncation is exactly
# the kind of subtle bug that's hard to notice until it causes confusion.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """Turn a plaintext password into a bcrypt hash safe to store in the DB."""
    password_bytes = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    # gensalt() generates a fresh random salt each call, so hashing the same
    # password twice produces two different (but both valid) hashes — this is
    # what stops attackers from spotting "these two users have the same
    # password" just by comparing hashed_password values.
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a plaintext password attempt against a stored bcrypt hash.

    Returns True/False rather than raising — callers (login) just want a
    yes/no answer, and a malformed stored hash should be treated as "no
    match" rather than crashing the request.
    """
    password_bytes = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# JWT helpers
# ─────────────────────────────────────────────────────────────────────────────
#
# A JWT has three parts: header, payload (a.k.a. "claims"), and signature.
# We put two custom claims in every token:
#   - "sub" (subject)  -> the user's id, as a string (JWT claims must be JSON-
#                          serialisable; UUID isn't, so we stringify it)
#   - "type"           -> "access" or "refresh", so a refresh token can't be
#                          replayed as an access token (or vice versa) even
#                          though both are signed with the same secret
# Refresh tokens additionally carry a "jti" (JWT ID) — a random unique id for
# that specific token, used as a handle when we hash-and-store it in the DB.


def _now() -> datetime:
    # Always work in UTC for token timestamps — comparing naive/local
    # datetimes against `exp` claims (which JWT libraries treat as UTC unix
    # timestamps) is a classic source of off-by-some-hours bugs.
    return datetime.now(timezone.utc)


def create_access_token(user_id: uuid.UUID) -> str:
    """Issue a short-lived access token identifying `user_id`.

    The caller (a route handler) sends this back in the response body; the
    client attaches it as `Authorization: Bearer <token>` on subsequent
    requests. `get_current_user` (deps/auth.py) verifies it on every request
    WITHOUT hitting the database — that's the whole point of a signed token.
    """
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": _now() + ACCESS_TOKEN_EXPIRE,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str, datetime]:
    """Issue a long-lived refresh token for `user_id`.

    Returns a 3-tuple of:
      - the raw JWT string (goes in the HttpOnly cookie sent to the client —
        never stored in the DB)
      - the token's `jti` (a random unique id — used by auth_service to build
        the `token_hash` row so reuse can be detected later)
      - the token's expiry as a timezone-aware datetime (stored in
        `refresh_tokens.expires_at` so the DB row's lifetime matches the JWT's)
    """
    jti = str(uuid.uuid4())
    expires_at = _now() + REFRESH_TOKEN_EXPIRE
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, jti, expires_at


def decode_token(token: str, expected_type: str) -> dict:
    """Verify a JWT's signature and expiry, and check it's the expected type.

    Raises `jwt.PyJWTError` (or a subclass) if the token is malformed,
    expired, has a bad signature, or — via our own check — is the wrong
    `type` (e.g. someone tries to use a refresh token as an access token).
    Callers should catch this and turn it into an HTTP 401.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a '{expected_type}' token, got '{payload.get('type')}'")
    return payload
