"""Orquestacion de operaciones de listings contra MELI y persistencia.

Operaciones:
  - publish: POST /items -> guarda mapeo id_cms/item_id
  - update: PUT /items/{id}
  - upgrade: POST /items/{id}/listing_type
  - get_status: GET /items/{id}
  - delete: DELETE /items/{id}
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.listings import store
from app.listings.builder import build_create, build_update
from app.listings.schema import CmsWebhookPayload, UpgradeListingRequest
from app.meli.client import MeliClient
from app.meli.errors import MeliError

log = get_logger(__name__)


async def publish(cms_payload: CmsWebhookPayload) -> dict:
    """Publica inmueble o desarrollo (con variaciones) en MELI."""
    async with MeliClient() as client:
        body = build_create(cms_payload)
        # Marca pending en Mongo ANTES de llamar a MELI (idempotencia parcial).
        await store.upsert_mapping(
            cms_payload.id_cms,
            tipo=cms_payload.tipo,
            estado="pending",
            listing_type_id=cms_payload.meli_payload.listing_type_id,
            category_id=cms_payload.meli_payload.category_id,
        )
        try:
            resp = await client.publish_item(body)
        except MeliError as e:
            log.error("publish_failed", id_cms=cms_payload.id_cms, status=e.status_code, body=e.body)
            await store.set_estado(cms_payload.id_cms, "error", error={
                "status_code": e.status_code,
                "message": e.message,
                "cause": e.cause,
                "body": e.body,
                "ts": datetime.now(UTC).isoformat(),
            })
            raise

        item_id = resp.get("id")
        meli_status = resp.get("status")
        meli_substatus = resp.get("sub_status")
        log.info("publish_ok", id_cms=cms_payload.id_cms, item_id=item_id,
                 status=meli_status, sub_status=meli_substatus)
        # Anti pack_quota_exceeded: log warn si substatus vino asi.
        if meli_substatus and "pack_quota_exceeded" in meli_substatus:
            log.warning("pack_quota_exceeded", id_cms=cms_payload.id_cms, item_id=item_id)

        await store.upsert_mapping(
            cms_payload.id_cms,
            item_id=item_id,
            tipo=cms_payload.tipo,
            estado=_meli_status_to_estado(meli_status),
            listing_type_id=resp.get("listing_type_id") or cms_payload.meli_payload.listing_type_id,
            category_id=resp.get("category_id") or cms_payload.meli_payload.category_id,
            meli_response=_slim_meli_response(resp),
        )
        return {"item_id": item_id, "status": meli_status, "sub_status": meli_substatus}


async def update(id_cms: str, cms_payload: CmsWebhookPayload) -> dict:
    existing = await store.get_by_id_cms(id_cms)
    if not existing or not existing.get("item_id"):
        raise ValueError(f"No existe mapeo para id_cms={id_cms} (no publicado o eliminado)")

    item_id: str = existing["item_id"]
    async with MeliClient() as client:
        body = build_update(cms_payload)
        try:
            resp = await client.update_item(item_id, body)
        except MeliError as e:
            log.error("update_failed", id_cms=id_cms, item_id=item_id,
                       status=e.status_code, body=e.body)
            await store.set_estado(id_cms, "error", error={
                "status_code": e.status_code,
                "message": e.message,
                "cause": e.cause,
                "ts": datetime.now(UTC).isoformat(),
            })
            raise

        meli_status = resp.get("status") if isinstance(resp, dict) else None
        await store.upsert_mapping(
            id_cms,
            item_id=item_id,
            estado=_meli_status_to_estado(meli_status) if meli_status else "active",
            meli_response=resp if isinstance(resp, dict) else None,
        )
        log.info("update_ok", id_cms=id_cms, item_id=item_id, status=meli_status)
        return {"item_id": item_id, "status": meli_status}


async def upgrade(id_cms: str, req: UpgradeListingRequest) -> dict:
    existing = await store.get_by_id_cms(id_cms)
    if not existing or not existing.get("item_id"):
        raise ValueError(f"No existe mapeo para id_cms={id_cms}")

    item_id: str = existing["item_id"]
    async with MeliClient() as client:
        try:
            # Anti-pie: validar listing_types disponibles del sitio antes de enviar.
            # (gold_premium NO existe en MLM; gold_pro es Oro Premium)
            resp = await client.change_listing_type(item_id, req.listing_type_id)
        except MeliError as e:
            log.error("upgrade_failed", id_cms=id_cms, item_id=item_id,
                       status=e.status_code, body=e.body)
            raise

        await store.upsert_mapping(
            id_cms,
            item_id=item_id,
            listing_type_id=req.listing_type_id,
            meli_response=resp if isinstance(resp, dict) else None,
        )
        log.info("upgrade_ok", id_cms=id_cms, item_id=item_id, listing_type=req.listing_type_id)
        return {"item_id": item_id, "listing_type_id": req.listing_type_id}


async def get_status(id_cms: str) -> dict:
    existing = await store.get_by_id_cms(id_cms)
    if not existing or not existing.get("item_id"):
        raise ValueError(f"No existe mapeo para id_cms={id_cms}")

    item_id: str = existing["item_id"]
    async with MeliClient() as client:
        try:
            resp = await client.get_item(item_id)
        except MeliError as e:
            log.error("get_status_failed", id_cms=id_cms, item_id=item_id,
                       status=e.status_code, body=e.body)
            raise

        meli_status = resp.get("status")
        await store.upsert_mapping(
            id_cms,
            item_id=item_id,
            estado=_meli_status_to_estado(meli_status),
            meli_response=_slim_meli_response(resp),
        )
        # Devolvemos al CMS el estado real + datos utiles para su panel
        # (permalink/thumbnail para mostrar, fechas para control, metricas,
        # y bandera de recategorizacion para accionar).
        return {
            "item_id": item_id,
            "status": meli_status,
            "sub_status": resp.get("sub_status"),
            "category_id": resp.get("category_id"),
            # Verifico si MELI recategorizo (regla oct 2025)
            "recategorized": existing.get("category_id") != resp.get("category_id"),
            "listing_type_id": resp.get("listing_type_id"),
            "domain_id": resp.get("domain_id"),
            "permalink": resp.get("permalink"),
            "thumbnail": resp.get("thumbnail"),
            "health": resp.get("health"),
            "available_quantity": resp.get("available_quantity"),
            "sold_quantity": resp.get("sold_quantity"),
            "date_created": resp.get("date_created"),
            "last_updated": resp.get("last_updated"),
            "expiration_time": resp.get("expiration_time"),
            "seller_contact": resp.get("seller_contact"),
            "variations": resp.get("variations"),
        }


async def delete(id_cms: str) -> dict:
    """Eliminacion DEFINITIVA segun MELI. No se puede revertir."""
    existing = await store.get_by_id_cms(id_cms)
    if not existing or not existing.get("item_id"):
        raise ValueError(f"No existe mapeo para id_cms={id_cms}")

    item_id: str = existing["item_id"]
    async with MeliClient() as client:
        try:
            await client.delete_item(item_id)
        except MeliError as e:
            log.error("delete_failed", id_cms=id_cms, item_id=item_id,
                       status=e.status_code, body=e.body)
            raise

        await store.set_estado(id_cms, "deleted")
        log.info("delete_ok", id_cms=id_cms, item_id=item_id)
        return {"item_id": item_id, "deleted": True}


# ───── helpers ─────

def _meli_status_to_estado(s: str | None) -> str:
    map_ = {"active": "active", "paused": "pending", "closed": "closed", "under_review": "pending"}
    return map_.get(s or "", "pending")


def _slim_meli_response(resp: dict[str, Any]) -> dict[str, Any]:
    # Solo guardamos campos utiles de la respuesta (no todo el item).
    # CMS los consume via get_status(); no guardamos internals (seller_address,
    # deal_ids, item_relations, warnings) que son del vendedor o de control MELI.
    keys = (
        "id", "status", "sub_status", "category_id", "listing_type_id",
        "start_time", "stop_time", "end_time", "expiration_time", "permalink",
        "thumbnail", "thumbnail_id", "health",
        "available_quantity", "sold_quantity",
        "date_created", "last_updated", "domain_id",
        "seller_contact", "variations",
    )
    return {k: resp.get(k) for k in keys if k in resp}
