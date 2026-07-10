"""Webhook receptor de notificaciones MELI (myalerts / feeds).

Trafico -> microservicio bidireccional. Topics disponibles (segun guia):
  - items                           : cambios de estado de articulos (incl. recategorizacion)
  - quotations                      : cotizaciones en desarrollos inmobiliarios
  - VIS Leads / questions           : contactos de interesados
  - classifieds_report              : (futuro) reportes de moderacion

Como el topic "items" dispara recategorizaciones automaticas (regla oct-2025),
lo almacenamos en Mongo para sincronizar el mapeo id_cms<->item_id despues.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.core.db import get_db
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/meli/notifications", tags=["meli-notifications"])

COLLECTION = "meli_notifications"
TOPICS_HABILITADOS = {"items", "quotations", "VIS Leads", "questions",
                     "classifieds_report", "leads_questions"}


@router.post("", status_code=status.HTTP_200_OK)
async def receive(request: Request) -> dict:
    """MELI llama aqui cuando un topic suscrito dispara una notificacion.

    Estructura tipica enviada por MELI:
      {"user_id": 123, "resource": "/items/MLM123456789",
       "topic": "items", "sent": "2024-...",
       "received": "2024-...", "application_id": 12345, "attempts": 1}
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        body = (await request.body()).decode(errors="ignore")
        log.error("meli_notification_bad_json", body=body[:500])
        raise HTTPException(400, "JSON invalido")

    topic = (payload.get("topic") or "").strip()
    resource = payload.get("resource") or ""
    user_id = payload.get("user_id")

    log.info("meli_notification_received", topic=topic, resource=resource, user_id=user_id)

    if topic not in TOPICS_HABILITADOS:
        log.info("meli_notification_ignored_unknown_topic", topic=topic)
        return {"status": "ignored", "reason": "topic_not_subscribed"}

    # Persistimos la notificacion (procesamiento async futuro). Idempotente por attempts.
    await get_db()[COLLECTION].update_one(
        {"resource": resource, "topic": topic},
        {
            "$set": {
                "resource": resource,
                "topic": topic,
                "user_id": user_id,
                "sent": payload.get("sent"),
                "received": payload.get("received"),
                "attempts": payload.get("attempts"),
                "raw": payload,
                "stored_at": datetime.now(UTC),
            }
        },
        upsert=True,
    )

    # Lugar reservado para reaccion futuro (ej: recategorizacion automatica,
    # actualizacion de estado del listing en Mongo cuando topic=items).
    if topic == "items" and resource.startswith("/items/"):
        item_id = resource.split("/")[-1]
        log.info("meli_items_notification_todo", item_id=item_id)
        # TODO futuro: implementar sync de recategorizacion:
        #   from app.listings.service import get_status_by_item_id
        #   await get_status_by_item_id(item_id)
        #   refresca category_id en Mongo si cambio (regla oct-2025)

    if topic in ("quotations", "VIS Leads", "leads_questions"):
        # TODO futuro: emitir a COLA leads para que un worker construya email al CRM.
        log.info("meli_lead_or_quotation_received", topic=topic, resource=resource)

    return {"status": "ok", "topic": topic, "resource": resource}


@router.get("/list")
async def list_recent(limit: int = 50) -> dict:
    """Endpoint de debugging: lista notificaciones MELI recientes."""
    cursor = get_db()[COLLECTION].find().sort("stored_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    # Serializar _id
    for d in docs:
        d["_id"] = str(d.get("_id"))
    return {"count": len(docs), "items": docs}
