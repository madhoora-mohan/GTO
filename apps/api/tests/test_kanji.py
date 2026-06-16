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


async def test_kanji_detail_includes_vocab_words(client, auth_headers):
    resp = await client.get("/kanji/食", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "vocab_words" in data
    assert isinstance(data["vocab_words"], list)
    assert len(data["vocab_words"]) <= 20
    for entry in data["vocab_words"]:
        assert "id" in entry
        assert "word" in entry
        assert "reading" in entry
        assert "meanings" in entry
        assert "reading_type" in entry
        assert entry["reading_type"] in ("on", "kun", None)


async def test_kanji_vocab_reading_types_for_food_kanji(client, auth_headers):
    resp = await client.get("/kanji/食", headers=auth_headers)
    assert resp.status_code == 200
    words = resp.json()["vocab_words"]
    reading_types = {w["word"]: w["reading_type"] for w in words}
    if "食べる" in reading_types:
        assert reading_types["食べる"] == "kun"
    if "食事" in reading_types:
        assert reading_types["食事"] == "on"


async def test_kanji_detail_includes_classical_radical(client, auth_headers):
    resp = await client.get("/kanji/食", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "classical_radical_number" in data
    assert "classical_radical_char" in data


async def test_kanji_list_does_not_include_vocab_words(client):
    resp = await client.get("/kanji")
    assert resp.status_code == 200
    for item in resp.json()["data"]:
        assert "vocab_words" not in item
