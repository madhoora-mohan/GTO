import pytest

ENDPOINTS = ["/kana", "/kanji", "/vocab", "/sentences", "/components"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_default_page_size(client, endpoint):
    resp = await client.get(endpoint)
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["data"]) <= 20


async def test_components_page_slice(client):
    full = await client.get("/components", params={"page_size": 100})
    resp = await client.get("/components", params={"page": 2, "page_size": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 2
    assert body["page_size"] == 5
    assert len(body["data"]) == 5
    assert body["total"] == full.json()["total"]
    assert body["data"] == full.json()["data"][5:10]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_page_size_over_max_returns_422(client, endpoint):
    resp = await client.get(endpoint, params={"page_size": 101})
    assert resp.status_code == 422
