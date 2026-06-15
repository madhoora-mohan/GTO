async def test_list_components(client):
    resp = await client.get("/components")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["total"] == 253


async def test_get_component(client):
    resp = await client.get("/components/2")
    assert resp.status_code == 200
    assert resp.json()["id"] == 2


async def test_get_component_not_found(client):
    resp = await client.get("/components/999999")
    assert resp.status_code == 404
