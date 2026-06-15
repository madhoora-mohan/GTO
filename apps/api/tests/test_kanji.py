async def test_list_kanji(client):
    resp = await client.get("/kanji")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "total" in body


async def test_list_kanji_filter_jlpt(client):
    resp = await client.get("/kanji", params={"jlpt": "N5"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(row["jlpt"] == "N5" for row in body["data"])


async def test_list_kanji_filter_stroke_count(client):
    resp = await client.get("/kanji", params={"stroke_count": 4})
    assert resp.status_code == 200
    body = resp.json()
    assert all(row["stroke_count"] == 4 for row in body["data"])


async def test_get_kanji_requires_auth(client):
    resp = await client.get("/kanji/日")
    assert resp.status_code == 401


async def test_get_kanji_with_auth(client, auth_headers):
    resp = await client.get("/kanji/日", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["character"] == "日"
    assert "components" in body
    assert "sentences" in body
    assert "user_mnemonic" in body
    assert body["user_mnemonic"] is None
    assert "mnemonic" in body


async def test_get_kanji_sentences_capped(client, auth_headers):
    resp = await client.get("/kanji/日", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["sentences"]) <= 10


async def test_get_kanji_not_found(client, auth_headers):
    resp = await client.get("/kanji/$", headers=auth_headers)
    assert resp.status_code == 404


async def test_patch_mnemonic_requires_auth(client):
    resp = await client.patch("/kanji/日/mnemonic", json={"mnemonic": "test"})
    assert resp.status_code == 401


async def test_patch_mnemonic_set(client, auth_headers):
    resp = await client.patch(
        "/kanji/日/mnemonic", json={"mnemonic": "sun mnemonic"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["character"] == "日"
    assert body["user_mnemonic"] == "sun mnemonic"


async def test_patch_mnemonic_clear(client, auth_headers):
    await client.patch(
        "/kanji/日/mnemonic", json={"mnemonic": "sun mnemonic"}, headers=auth_headers
    )
    resp = await client.patch("/kanji/日/mnemonic", json={"mnemonic": ""}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["user_mnemonic"] is None


async def test_patch_mnemonic_not_found(client, auth_headers):
    resp = await client.patch(
        "/kanji/$/mnemonic", json={"mnemonic": "test"}, headers=auth_headers
    )
    assert resp.status_code == 404
