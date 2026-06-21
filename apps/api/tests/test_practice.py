async def test_kanji_practice_batch_requires_auth(client):
    resp = await client.get(
        "/kanji/practice-batch",
        params={"jlpt_level": "N5", "scope": "exact", "distribution": "balanced"},
    )
    assert resp.status_code == 401


async def test_kanji_practice_batch_shape(client, auth_headers):
    resp = await client.get(
        "/kanji/practice-batch",
        params={"jlpt_level": "N5", "scope": "exact", "distribution": "balanced", "count": 10},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) <= 10
    for item in data:
        assert item["jlpt"] == "N5"
        assert "components" not in item
        assert "sentences" not in item
        assert "vocab_words" not in item
        assert "user_mnemonic" not in item
        assert "distractor_meanings" in item
        assert len(item["distractor_meanings"]) <= 3


async def test_kanji_practice_batch_no_duplicates(client, auth_headers):
    resp = await client.get(
        "/kanji/practice-batch",
        params={"jlpt_level": "N3", "scope": "and_below", "distribution": "balanced", "count": 30},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    characters = [item["character"] for item in resp.json()["data"]]
    assert len(characters) == len(set(characters))


async def test_kanji_practice_batch_respects_exclude(client, auth_headers):
    first = await client.get(
        "/kanji/practice-batch",
        params={"jlpt_level": "N5", "scope": "exact", "distribution": "balanced", "count": 20},
        headers=auth_headers,
    )
    excluded = [item["character"] for item in first.json()["data"]]

    second = await client.get(
        "/kanji/practice-batch",
        params={
            "jlpt_level": "N5",
            "scope": "exact",
            "distribution": "balanced",
            "count": 20,
            "exclude": ",".join(excluded),
        },
        headers=auth_headers,
    )
    assert second.status_code == 200
    second_characters = {item["character"] for item in second.json()["data"]}
    assert second_characters.isdisjoint(excluded)


async def test_kanji_practice_batch_distractors_dont_overlap_own_meanings(client, auth_headers):
    resp = await client.get(
        "/kanji/practice-batch",
        params={"jlpt_level": "N5", "scope": "exact", "distribution": "balanced", "count": 20},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    for item in resp.json()["data"]:
        own_meanings = set(item["meanings"])
        assert own_meanings.isdisjoint(item["distractor_meanings"])


async def test_vocab_practice_batch_requires_auth(client):
    resp = await client.get(
        "/vocab/practice-batch",
        params={"jlpt_level": "N5", "scope": "exact", "distribution": "balanced"},
    )
    assert resp.status_code == 401


async def test_vocab_practice_batch_shape(client, auth_headers):
    resp = await client.get(
        "/vocab/practice-batch",
        params={"jlpt_level": "N5", "scope": "exact", "distribution": "balanced", "count": 10},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) <= 10
    for item in data:
        assert item["jlpt"] == "N5"
        assert item["sentences"] is None
        assert "distractor_meanings" in item


async def test_vocab_practice_batch_no_duplicates(client, auth_headers):
    resp = await client.get(
        "/vocab/practice-batch",
        params={"jlpt_level": "N3", "scope": "and_below", "distribution": "challenge", "count": 30},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["data"]]
    assert len(ids) == len(set(ids))


async def test_sentence_cloze_requires_auth(client):
    resp = await client.get(
        "/practice/sentence-cloze",
        params={
            "source": "vocab",
            "jlpt_level": "N5",
            "scope": "exact",
            "distribution": "balanced",
        },
    )
    assert resp.status_code == 401


async def test_sentence_cloze_vocab_source_shape(client, auth_headers):
    resp = await client.get(
        "/practice/sentence-cloze",
        params={
            "source": "vocab",
            "jlpt_level": "N5",
            "scope": "exact",
            "distribution": "balanced",
            "count": 5,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    for item in data:
        assert "___" in item["sentence_japanese"]
        assert item["blanked_word"] not in item["sentence_japanese"]
        assert len(item["options"]) == 4
        assert item["blanked_word"] in item["options"]
        assert len(set(item["options"])) == 4


async def test_sentence_cloze_kanji_source_shape(client, auth_headers):
    resp = await client.get(
        "/practice/sentence-cloze",
        params={
            "source": "kanji",
            "jlpt_level": "N5",
            "scope": "exact",
            "distribution": "balanced",
            "count": 5,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    for item in data:
        assert "___" in item["sentence_japanese"]
        assert item["blanked_word"] not in item["sentence_japanese"]
        assert len(item["options"]) == 4
        assert item["blanked_word"] in item["options"]
        assert len(set(item["options"])) == 4


async def test_sentence_cloze_no_duplicate_sentences(client, auth_headers):
    resp = await client.get(
        "/practice/sentence-cloze",
        params={
            "source": "vocab",
            "jlpt_level": "N3",
            "scope": "and_below",
            "distribution": "balanced",
            "count": 15,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    sentences = [item["sentence_japanese"] for item in resp.json()["data"]]
    assert len(sentences) == len(set(sentences))
