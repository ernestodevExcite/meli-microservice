"""Capa de mapeo: payload del CMS -> JSON MELI.

Hoy el CMS se adaptara para enviar ya en formato MELI (schema: meli_payload).
Este builder:
  1. Valida el DTO con Pydantic (schema.py).
  2. Lo normaliza a dict listo para POST/PUT.
  3. Verifica reglas MLM especificas (gold_pro no gold_premium, imagenes, etc).
"""
from __future__ import annotations

from app.listings.schema import CmsWebhookPayload, MeliItemCreate, MeliItemUpdate


def build_create(payload: CmsWebhookPayload) -> dict:
    item: MeliItemCreate = payload.meli_payload
    return item.to_meli()


def build_update(payload: CmsWebhookPayload | MeliItemUpdate) -> dict:
    if isinstance(payload, CmsWebhookPayload):
        # Si el CMS envia el payload completo (en webhook PUT), lo convertimos en update parcial.
        item = payload.meli_payload
        update = MeliItemUpdate(
            title=item.title,
            price=item.price,
            pictures=item.pictures,
            seller_contact=item.seller_contact,
            location=item.location,
            attributes=item.attributes,
            variations=item.variations,
            video_id=item.video_id,
        )
        return update.to_meli()
    return payload.to_meli()
