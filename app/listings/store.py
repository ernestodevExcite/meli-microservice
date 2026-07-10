"""Mapa id_cms <-> item_id MELI + estado de sync.

Coleccion mongo listings:
    _id: ObjectId
    id_cms: str (unique)
    item_id: str | null (unique sparse)
    tipo: "inmueble" | "desarrollo"
    estado: "pending" | "active" | "closed" | "error" | "deleted"
    listing_type_id: str | null
    category_id: str | null
    last_sync_at: datetime
    last_meli_status: dict | null
    error: dict | null
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from app.core.db import get_db

COLLECTION = "listings"

ListingEstado = Literal["pending", "active", "closed", "error", "deleted"]


async def upsert_mapping(
    id_cms: str,
    *,
    item_id: str | None = None,
    tipo: str = "inmueble",
    estado: ListingEstado = "pending",
    listing_type_id: str | None = None,
    category_id: str | None = None,
    meli_response: dict | None = None,
    error: dict | None = None,
) -> dict:
    db = get_db()
    set_fields: dict[str, object] = {
        "id_cms": id_cms,
        "tipo": tipo,
        "estado": estado,
        "last_sync_at": datetime.now(UTC),
    }
    if item_id is not None: set_fields["item_id"] = item_id
    if listing_type_id is not None: set_fields["listing_type_id"] = listing_type_id
    if category_id is not None: set_fields["category_id"] = category_id
    if meli_response is not None: set_fields["last_meli_status"] = meli_response
    if error is not None: set_fields["error"] = error

    await db[COLLECTION].update_one(
        {"id_cms": id_cms},
        {"$set": set_fields, "$setOnInsert": {"created_at": datetime.now(UTC)}},
        upsert=True,
    )
    doc = await db[COLLECTION].find_one({"id_cms": id_cms})
    return doc or {}


async def get_by_id_cms(id_cms: str) -> dict | None:
    db = get_db()
    return await db[COLLECTION].find_one({"id_cms": id_cms})


async def get_by_item_id(item_id: str) -> dict | None:
    db = get_db()
    return await db[COLLECTION].find_one({"item_id": item_id})


async def set_estado(id_cms: str, estado: ListingEstado, *, error: dict | None = None) -> None:
    db = get_db()
    update: dict[str, object] = {"estado": estado, "last_sync_at": datetime.now(UTC)}
    if error is not None:
        update["error"] = error
    await db[COLLECTION].update_one({"id_cms": id_cms}, {"$set": update})
