async def test_list_passages_public(client):
    resp = await client.get("/reading/passages")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "total" in body


async def test_get_passage_requires_auth(client):
    resp = await client.get("/reading/passages/1")
    assert resp.status_code == 401


async def test_get_passage_not_found_with_auth(client, auth_headers):
    resp = await client.get("/reading/passages/999999", headers=auth_headers)
    assert resp.status_code == 404
