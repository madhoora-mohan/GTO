async def test_list_vocab(client):
    resp = await client.get("/vocab")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "total" in body


async def test_list_vocab_filter_jlpt(client):
    resp = await client.get("/vocab", params={"jlpt": "N5"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(row["jlpt"] == "N5" for row in body["data"])


async def test_list_vocab_filter_is_common(client):
    resp = await client.get("/vocab", params={"is_common": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(row["is_common"] is True for row in body["data"])


async def test_list_vocab_search(client):
    resp = await client.get("/vocab", params={"search": "食"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    assert all("食" in row["word"] or "食" in row["reading"] for row in body["data"])


async def test_get_vocab(client):
    resp = await client.get("/vocab/1158780")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "1158780"
    assert "sentences" in body


async def test_get_vocab_sentences_capped(client):
    resp = await client.get("/vocab/1008490")
    assert resp.status_code == 200
    assert len(resp.json()["sentences"]) <= 10


async def test_get_vocab_sentence_jlpt_filter(client):
    resp = await client.get("/vocab/1008490", params={"sentence_jlpt": "N5"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sentences"]) <= 10
    assert all(s["jlpt"] == "N5" for s in body["sentences"])


async def test_get_vocab_sentence_jlpt_max_filter(client):
    resp = await client.get("/vocab/1008490", params={"sentence_jlpt_max": "N3"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sentences"]) <= 10
    assert all(s["jlpt"] in ("N3", "N4", "N5") for s in body["sentences"])


async def test_get_vocab_sentence_jlpt_conflicting_params(client):
    resp = await client.get(
        "/vocab/1008490", params={"sentence_jlpt": "N5", "sentence_jlpt_max": "N3"}
    )
    assert resp.status_code == 422


async def test_get_vocab_not_found(client):
    resp = await client.get("/vocab/0")
    assert resp.status_code == 404
