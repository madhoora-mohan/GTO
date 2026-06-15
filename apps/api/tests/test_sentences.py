async def test_list_sentences(client):
    resp = await client.get("/sentences")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "total" in body


async def test_list_sentences_filter_jlpt(client):
    resp = await client.get("/sentences", params={"jlpt": "N5"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(row["jlpt"] == "N5" for row in body["data"])


async def test_list_sentences_search(client):
    resp = await client.get("/sentences", params={"search": "食べ"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    assert all("食べ" in row["japanese"] for row in body["data"])


async def test_get_sentence(client):
    resp = await client.get("/sentences/4702")
    assert resp.status_code == 200
    assert resp.json()["id"] == 4702


async def test_get_sentence_not_found(client):
    resp = await client.get("/sentences/999999999")
    assert resp.status_code == 404
