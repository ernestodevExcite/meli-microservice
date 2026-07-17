"""Tests de endpoints sin Mongo real: validamos que los /docs y /healthz arranquen."""
from __future__ import annotations

from unittest.mock import patch

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


def _valid_publish_payload() -> dict:
    return {
        "id_cms": "cms-001",
        "tipo": "inmueble",
        "meli_payload": {
            "category_id": "MLM170531",
            "title": "Casa En Venta, Mérida",
            "price": 1000000,
            "currency_id": "MXN",
            "buying_mode": "classified",
            "listing_type_id": "gold_pro",
            "available_quantity": 1,
            "condition": "new",
            "channels": ["marketplace"],
            "pictures": [{"source": "https://example.com/1.jpg"}],
            "location": {
                "address_line": "Calle 50 100",
                "city_id": "TUxNQ03JUjU5NTY",
                "state_id": "TUxNUFlVQzc1OTk",
                "country_id": "MX",
            },
            "attributes": [
                {"id": "OPERATION", "value_id": "242075", "value_name": "Venta"},
                {"id": "PROPERTY_TYPE", "value_id": "242060", "value_name": "Casa"},
            ],
        },
    }


@pytest.mark.asyncio
async def test_publish_quota_error_devuelve_402_no_502(client):
    """Caso real: MELI responde 400 'Not available quota' (cuota agotada).

    Antes se enmascaraba como 502 Bad Gateway. Ahora debe llegar como 402
    Payment Required con body estructurado, para que el CMS pueda distinguirlo
    de un 502 (upstream caido) y pedir mas cuota al vendedor.
    """
    from app.meli.errors import MeliQuotaError

    fake_err = MeliQuotaError(
        400, "Not available quota", cause=[],
        body={"error": "bad_request", "message": "Not available quota", "cause": []},
    )
    with patch("app.listings.router.service.publish", side_effect=fake_err):
        resp = await client.post("/listings", json=_valid_publish_payload())

    assert resp.status_code == 402, resp.text
    body = resp.json()
    assert body["error"] == "meli_api_error"
    assert body["meli_status"] == 400
    assert body["meli_error_code"] == "bad_request"
    assert body["message"] == "Not available quota"


@pytest.mark.asyncio
async def test_publish_validation_error_devuelve_400(client):
    """Un 400 validation_error real (con cause) -> 400 al CMS, no 502."""
    from app.meli.errors import MeliValidationError

    fake_err = MeliValidationError(
        400, "falta OPERATION", cause=[{"code": "missing.attribute"}],
        body={"error": "validation_error", "message": "falta OPERATION"},
    )
    with patch("app.listings.router.service.publish", side_effect=fake_err):
        resp = await client.post("/listings", json=_valid_publish_payload())

    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "meli_api_error"
    assert body["meli_status"] == 400
    assert body["message"] == "falta OPERATION"
    assert body["cause"] == [{"code": "missing.attribute"}]


@pytest.mark.asyncio
async def test_publish_server_error_devuelve_502(client):
    """Un 500 de MELI que agota retry -> 502 Bad Gateway al CMS."""
    from app.meli.errors import MeliServerError

    fake_err = MeliServerError(
        500, "internal_server_error", body={"error": "internal_server_error"},
    )
    with patch("app.listings.router.service.publish", side_effect=fake_err):
        resp = await client.post("/listings", json=_valid_publish_payload())

    assert resp.status_code == 502, resp.text
    body = resp.json()
    assert body["meli_status"] == 500


@pytest.mark.asyncio
async def test_publish_rate_limit_devuelve_429(client):
    """Un 429 que agota retry -> 429 al CMS."""
    from app.meli.errors import MeliRateLimitError

    fake_err = MeliRateLimitError(429, "too_many_requests", body={"error": "too_many_requests"})
    with patch("app.listings.router.service.publish", side_effect=fake_err):
        resp = await client.post("/listings", json=_valid_publish_payload())

    assert resp.status_code == 429, resp.text
