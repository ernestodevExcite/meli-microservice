"""Tests del schema Pydantic: validacion de reglasMELI (MLM)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.listings.schema import (
    CmsWebhookPayload,
    MeliAttribute,
    MeliItemCreate,
    MeliItemUpdate,
    UpgradeListingRequest,
)


def _base_item() -> dict:
    return {
        "category_id": "MLM1459",
        "title": "Casa 3 recamaras Polanco",
        "price": 5_000_000,
        "currency_id": "MXN",
        "listing_type_id": "silver",
        "condition": "not_specified",
        "channels": ["marketplace"],
        "pictures": [{"source": "https://img.example.com/foto1.jpg"}],
        "seller_contact": {"contact": "Ana", "email": "ana@test.com", "phone": "5512345678"},
        "location": {
            "address_line": "Av. Reforma 100",
            "state_id": "MX-DIF",
        },
        "attributes": [
            {"id": "TOTAL_AREA", "value_name": 200},
            {"id": "OPERATION", "value_id": "242075", "value_name": "Venta"},
        ],
    }


def test_item_create_ok() -> None:
    item = MeliItemCreate(**_base_item())
    body = item.to_meli()
    assert body["buying_mode"] == "classified"
    assert body["available_quantity"] == 1
    assert body["pictures"][0]["source"] == "https://img.example.com/foto1.jpg"


def test_item_create_sin_imagenes_rechazado() -> None:
    data = _base_item()
    data["pictures"] = []
    # Pydantic valida min_length=1 en el Field (... Feb 2026 ya documentoтора)
    with pytest.raises(ValidationError):
        MeliItemCreate(**data)


def test_address_line_sin_numero_rechazado() -> None:
    data = _base_item()
    data["location"] = {"address_line": "Av Reforma sin numero"}
    with pytest.raises(ValidationError):
        MeliItemCreate(**data)


def test_gold_pro_permitido_gold_premium_rechazado() -> None:
    # Literal ya bloquea gold_premium en ListingType
    data = _base_item()
    data["listing_type_id"] = "gold_premium"
    with pytest.raises(ValidationError):
        MeliItemCreate(**data)
    data["listing_type_id"] = "gold_pro"
    item = MeliItemCreate(**data)
    assert item.listing_type_id == "gold_pro"


def test_attribute_sin_value_rechazado() -> None:
    with pytest.raises(ValidationError):
        MeliAttribute(id="TOTAL_AREA")


def test_variations_para_desarrollo() -> None:
    data = _base_item()
    data["variations"] = [
        {
            "price": 1_500_000,
            "attribute_combinations": [{"id": "BEDROOMS", "value_name": 2}],
            "picture_ids": ["123_ML_abc"],
        }
    ]
    item = MeliItemCreate(**data)
    body = item.to_meli()
    assert body["variations"][0]["price"] == 1_500_000


def test_to_meli_update_partial() -> None:
    upd = MeliItemUpdate(price=5_500_000, title="Casa 3 rec Polanco - actualizada")
    out = upd.to_meli()
    assert out == {"title": "Casa 3 rec Polanco - actualizada", "price": 5_500_000}


def test_cms_webhook_payload_ok() -> None:
    payload = {"id_cms": "cms-001", "tipo": "inmueble", "meli_payload": _base_item()}
    dto = CmsWebhookPayload(**payload)
    assert dto.id_cms == "cms-001"
    assert dto.meli_payload.price == 5_000_000


def test_upgrade_request_accepts_gold_pro_rejects_gold_premium() -> None:
    UpgradeListingRequest(listing_type_id="gold_pro")
    with pytest.raises(ValidationError):
        UpgradeListingRequest(listing_type_id="gold_premium")
