# WHAT: Shared pytest fixtures — a transactional DB session, an HTTP client
#       wired to use it, and an auth-headers helper.
# WHY:  Every test needs a client that talks to the real Neon schema but
#       leaves no trace, and most content tests need a logged-in user.

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import get_db
from app.core.limiter import limiter
from app.main import app


@pytest.fixture
async def db_session():
    # NullPool + function-scoped: each test gets its own connection on its
    # own event loop, then closes it. A session- or module-scoped engine
    # would hand out a pooled asyncpg connection bound to a *previous* test's
    # event loop, which asyncpg refuses ("another operation is in progress").
    engine = create_async_engine(
        settings.async_database_url, connect_args={"ssl": "require"}, poolclass=NullPool
    )
    async with engine.connect() as conn:
        await conn.begin()
        session_factory = async_sessionmaker(conn, expire_on_commit=False)
        async with session_factory() as session:
            yield session
        await conn.rollback()
    await engine.dispose()


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Rate limiting is tested explicitly in test_rate_limiting.py. For every
    # other test, repeated calls to /auth/register and /auth/login (e.g. via
    # the auth_headers fixture, used across many test files) would otherwise
    # trip the in-memory limiter and turn unrelated tests flaky.
    limiter.enabled = False

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    limiter.enabled = True
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_headers(client):
    """Register a test user and return Bearer auth headers."""
    await client.post(
        "/auth/register", json={"email": "test@example.com", "password": "testpass123"}
    )
    resp = await client.post(
        "/auth/login", json={"email": "test@example.com", "password": "testpass123"}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
