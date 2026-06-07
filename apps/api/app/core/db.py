# WHAT: Sets up the *async* database connection that the FastAPI app uses at
#       request time (Alembic migrations use a separate, synchronous
#       connection — see migrations/env.py — because Alembic doesn't support
#       async).
# WHY:  Route handlers need a way to talk to Postgres without each one having
#       to open/close its own connection. This module builds one shared
#       connection pool (`engine`), a factory for sessions (`SessionLocal`),
#       and a FastAPI dependency (`get_db`) that route handlers can `Depends`
#       on to receive a ready-to-use session that's automatically cleaned up.
#
# The pieces, from the bottom up:
#   engine       -> the actual connection pool to Postgres (via asyncpg)
#   SessionLocal -> a factory that produces new AsyncSession objects
#   get_db       -> a FastAPI dependency that hands a route a session and
#                   guarantees it gets closed afterwards, even on error

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# `settings.async_database_url` rewrites the plain "postgresql://" URL to
# "postgresql+asyncpg://" so SQLAlchemy knows to use the asyncpg driver.
#
# `pool_pre_ping=True` makes SQLAlchemy run a tiny "is this connection still
# alive?" check before handing a pooled connection to your code. Neon (and
# other serverless/managed Postgres providers) can silently close idle
# connections, so without this you'd occasionally get a confusing
# "connection closed" error on the first query of a new request.
# `connect_args={"ssl": "require"}` tells asyncpg to use SSL when talking to
# Neon. We can't get this from the URL's query string the usual way — Neon's
# connection string spells it "sslmode=require" (a libpq/psycopg convention),
# which asyncpg's URL parser rejects outright. `async_database_url` strips
# that query param (see core/config.py); this is where we put the equivalent
# setting back, in the form asyncpg actually understands.
engine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=True,
    connect_args={"ssl": "require"},
)

# async_sessionmaker is a factory — calling SessionLocal() gives you a fresh
# AsyncSession bound to `engine`.
#
# `expire_on_commit=False` stops SQLAlchemy from "expiring" (clearing out)
# the attributes of objects you've loaded as soon as you commit a transaction.
# Without this, accessing an attribute on a model object *after* commit would
# trigger a fresh DB query — which fails for async sessions outside of an
# active `async with` block. Setting it to False lets you keep reading
# attributes off objects after commit, which is what FastAPI route handlers
# typically want to do (e.g. returning the freshly-created user in a response).
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session for the lifetime of
    a single request.

    Usage in a route:
        @router.get("/something")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...

    The `async with` block ensures the session is always closed when the
    request finishes — whether it succeeded, raised an exception, or the
    client disconnected early.
    """
    async with SessionLocal() as session:
        yield session
