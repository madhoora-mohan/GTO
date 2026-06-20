from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.models.user import User
from app.models.user_mnemonic import UserMnemonic


async def test_list_my_mnemonics_requires_auth(client):
    resp = await client.get("/users/me/mnemonics")
    assert resp.status_code == 401


async def test_list_my_mnemonics_empty(client, auth_headers):
    resp = await client.get("/users/me/mnemonics", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["total"] == 0


async def test_list_my_mnemonics_only_includes_customized_kanji(client, auth_headers):
    await client.patch("/kanji/日/mnemonic", json={"mnemonic": "sun mnemonic"}, headers=auth_headers)

    resp = await client.get("/users/me/mnemonics", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["character"] == "日"
    assert body["data"][0]["user_mnemonic"] == "sun mnemonic"
    assert "updated_at" in body["data"][0]


async def test_list_my_mnemonics_ordered_most_recent_first(client, auth_headers, db_session):
    await client.patch("/kanji/日/mnemonic", json={"mnemonic": "first"}, headers=auth_headers)
    await client.patch("/kanji/食/mnemonic", json={"mnemonic": "second"}, headers=auth_headers)

    # Both PATCHes commit inside the same outer test transaction, so Postgres'
    # now() (transaction-start-time, not statement-time) gives them identical
    # updated_at values. Push 日's back explicitly so desc-ordering is
    # actually exercised instead of relying on wall-clock drift.
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    await db_session.execute(
        update(UserMnemonic)
        .where(UserMnemonic.user_id == user.id, UserMnemonic.kanji_character == "日")
        .values(updated_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )
    await db_session.commit()

    resp = await client.get("/users/me/mnemonics", headers=auth_headers)
    assert resp.status_code == 200
    characters = [row["character"] for row in resp.json()["data"]]
    assert characters[0] == "食"
    assert characters[1] == "日"


async def test_list_my_mnemonics_excludes_cleared(client, auth_headers):
    await client.patch("/kanji/日/mnemonic", json={"mnemonic": "sun mnemonic"}, headers=auth_headers)
    await client.patch("/kanji/日/mnemonic", json={"mnemonic": ""}, headers=auth_headers)

    resp = await client.get("/users/me/mnemonics", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_list_my_mnemonics_pagination(client, auth_headers):
    await client.patch("/kanji/日/mnemonic", json={"mnemonic": "first"}, headers=auth_headers)
    await client.patch("/kanji/食/mnemonic", json={"mnemonic": "second"}, headers=auth_headers)

    resp = await client.get(
        "/users/me/mnemonics", params={"page": 1, "page_size": 1}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 1


async def test_list_my_mnemonics_scoped_to_user(client, auth_headers):
    await client.patch("/kanji/日/mnemonic", json={"mnemonic": "mine"}, headers=auth_headers)

    await client.post(
        "/auth/register", json={"email": "other-user@example.com", "password": "testpass123"}
    )
    login = await client.post(
        "/auth/login", json={"email": "other-user@example.com", "password": "testpass123"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get("/users/me/mnemonics", headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
