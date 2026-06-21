async def test_crossword_requires_auth(client):
    resp = await client.get(
        "/vocab/crossword",
        params={"jlpt_level": "N5", "scope": "exact", "distribution": "balanced"},
    )
    assert resp.status_code == 401


async def test_crossword_shape(client, auth_headers):
    resp = await client.get(
        "/vocab/crossword",
        params={"jlpt_level": "N3", "scope": "and_below", "distribution": "balanced"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["insufficient"] is False
    assert body["width"] > 0
    assert body["height"] > 0
    assert len(body["words"]) >= 3
    assert len(body["cells"]) == body["width"] * body["height"]


async def test_crossword_words_interlock(client, auth_headers):
    resp = await client.get(
        "/vocab/crossword",
        params={"jlpt_level": "N3", "scope": "and_below", "distribution": "balanced"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    words_by_id = {w["id"]: w for w in body["words"]}

    intersections = 0
    for cell in body["cells"]:
        if cell["blocked"]:
            assert cell["letter"] is None
            assert cell["word_ids"] == []
            continue
        assert cell["letter"] is not None
        letters_at_cell = set()
        for word_id in cell["word_ids"]:
            word = words_by_id[word_id]
            offset = (
                (cell["col"] - word["col"]) if word["direction"] == "across"
                else (cell["row"] - word["row"])
            )
            letters_at_cell.add(word["word"][offset])
        # Every word touching this cell must agree on the letter there.
        assert letters_at_cell == {cell["letter"]}
        if len(cell["word_ids"]) > 1:
            intersections += 1

    assert intersections >= 1


async def test_crossword_decoy_kana_not_used_in_answers(client, auth_headers):
    resp = await client.get(
        "/vocab/crossword",
        params={"jlpt_level": "N3", "scope": "and_below", "distribution": "balanced"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    used_kana = {cell["letter"] for cell in body["cells"] if not cell["blocked"]}
    assert used_kana.isdisjoint(body["decoy_kana"])


async def test_crossword_no_count_param_needed(client, auth_headers):
    # No `count` query param at all — the doc explicitly says this endpoint
    # determines word count from the generation algorithm, not a request param.
    resp = await client.get(
        "/vocab/crossword",
        params={"jlpt_level": "N5", "scope": "exact", "distribution": "challenge"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
