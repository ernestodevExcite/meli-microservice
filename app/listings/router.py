"""Router FastAPI con endpoints que el CMS llama via webhook."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.listings import service
from app.listings.schema import CmsWebhookPayload, UpgradeListingRequest

log = get_logger(__name__)
router = APIRouter(prefix="/listings", tags=["listings"])


async def verify_webhook(request: Request, x_cms_signature: str | None = Header(default=None)) -> None:
    """Valida HMAC-SHA256 del body si WEBHOOK_SECRET esta configurado."""
    settings = get_settings()
    if not settings.webhook_secret:
        return  # en dev/local no validamos

    if x_cms_signature is None:
        raise HTTPException(401, "Firma del webhook ausente (X-CMS-Signature)")

    body = await request.body()
    expected = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_cms_signature):
        raise HTTPException(401, "Firma del webhook invalida")


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_webhook)])
async def publish(payload: CmsWebhookPayload) -> dict:
    try:
        return await service.publish(payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("publish_endpoint_error", id_cms=payload.id_cms)
        raise HTTPException(502, f"Error MELI: {e}")


@router.put("/{id_cms}", dependencies=[Depends(verify_webhook)])
async def update(id_cms: str, payload: CmsWebhookPayload) -> dict:
    if payload.id_cms != id_cms:
        raise HTTPException(400, f"id_cms de path ({id_cms}) no coincide con body ({payload.id_cms})")
    try:
        return await service.update(id_cms, payload)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("update_endpoint_error", id_cms=id_cms)
        raise HTTPException(502, f"Error MELI: {e}")


@router.get("/{id_cms}")
async def get_status(id_cms: str) -> dict:
    try:
        return await service.get_status(id_cms)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("get_status_endpoint_error", id_cms=id_cms)
        raise HTTPException(502, f"Error MELI: {e}")


@router.post("/{id_cms}/upgrade", dependencies=[Depends(verify_webhook)])
async def upgrade(id_cms: str, req: UpgradeListingRequest) -> dict:
    try:
        return await service.upgrade(id_cms, req)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("upgrade_endpoint_error", id_cms=id_cms)
        raise HTTPException(502, f"Error MELI: {e}")


@router.delete("/{id_cms}", dependencies=[Depends(verify_webhook)])
async def delete(id_cms: str) -> dict:
    try:
        return await service.delete(id_cms)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("delete_endpoint_error", id_cms=id_cms)
        raise HTTPException(502, f"Error MELI: {e}")
