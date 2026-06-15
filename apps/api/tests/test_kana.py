async def test_list_kana(client):
    resp = await client.get("/kana")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "total" in body and "page" in body and "page_size" in body
    assert body["total"] == 214


async def test_list_kana_filter_type(client):
    resp = await client.get("/kana", params={"type": "hiragana"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(row["type"] == "hiragana" for row in body["data"])


async def test_list_kana_filter_category(client):
    resp = await client.get("/kana", params={"category": "dakuten"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(row["category"] == "dakuten" for row in body["data"])


async def test_get_kana_found(client):
    resp = await client.get("/kana/き")
    assert resp.status_code == 200
    assert resp.json()["character"] == "き"


async def test_get_kana_not_found(client):
    resp = await client.get("/kana/!!")
    assert resp.status_code == 404
