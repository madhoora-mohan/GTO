# WHAT: Verifies the slowapi rate limits on /auth/login and /auth/register.
# WHY:  The `client` fixture disables the limiter for every other test file
#       (so the auth_headers fixture doesn't trip it) — these tests need it
#       enabled, so they flip it back on for the duration of the test.

import pytest

from app.core.limiter import limiter


@pytest.fixture
def rate_limited_client(client):
    limiter.enabled = True
    yield client
    limiter.enabled = False


async def test_login_rate_limit(rate_limited_client):
    for i in range(10):
        resp = await rate_limited_client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "wrongpass"}
        )
        assert resp.status_code != 429

    resp = await rate_limited_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "wrongpass"}
    )
    assert resp.status_code == 429


async def test_register_rate_limit(rate_limited_client):
    for i in range(5):
        resp = await rate_limited_client.post(
            "/auth/register",
            json={"email": f"user{i}@example.com", "password": "testpass123"},
        )
        assert resp.status_code != 429

    resp = await rate_limited_client.post(
        "/auth/register", json={"email": "user5@example.com", "password": "testpass123"}
    )
    assert resp.status_code == 429
