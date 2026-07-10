"""Tests de endpoints sin Mongo real: validamos que los /docs y /healthz arranquen."""
from __future__ import annotations

import pytest

# test con cliente async de httpx via ASGITransport


@pytest.mark.asyncio
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_openapi_disponible(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    paths = list(schema["paths"].keys())
    assert "/healthz" in paths
    assert "/listings" in paths
    assert "/listings/{id_cms}/upgrade" in paths
    assert "/meli/notifications" in paths
