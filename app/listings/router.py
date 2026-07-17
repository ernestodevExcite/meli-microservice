"""Router FastAPI con endpoints que el CMS llama via webhook."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.listings import service
from app.listings.schema import CmsWebhookPayload, UpgradeListingRequest
from app.meli.errors import MeliError, http_status_for

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


def _log_and_reraise(e: MeliError, id_cms: str, op: str) -> None:
    """Log contextual (id_cms + op) y re-raise; el handler global traduce a HTTP.

    - 4xx de negocio MELI: WARN (ruido esperable, no requiere stacktrace).
    - 5xx de MELI o transitorios agotados: ERROR (upstream caido).
    El service ya logueo 'publish_failed'/'update_failed'/... con el body; aqui
    solo anadimos la capa de 'que endpoint y que id_cms' para trazabilidad.
    """
    http_status = http_status_for(e)
    log_fn = log.error if http_status >= 500 else log.warning
    log_fn(
        "meli_error_enpoint",
        op=op, id_cms=id_cms, meli_status=e.status_code,
        http_status=http_status, message=e.message, cause=e.cause,
    )
    raise e


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_webhook)])
async def publish(payload: CmsWebhookPayload) -> dict:
    try:
        return await service.publish(payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except MeliError as e:
        _log_and_reraise(e, payload.id_cms, "publish")
    except Exception as e:  # noqa: BLE001 - bug inesperado, no enmascarar como MELI
        log.exception("publish_endpoint_unexpected", id_cms=payload.id_cms)
        raise HTTPException(500, "Error interno del microservicio") from e


@router.put("/{id_cms}", dependencies=[Depends(verify_webhook)])
async def update(id_cms: str, payload: CmsWebhookPayload) -> dict:
    if payload.id_cms != id_cms:
        raise HTTPException(400, f"id_cms de path ({id_cms}) no coincide con body ({payload.id_cms})")
    try:
        return await service.update(id_cms, payload)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except MeliError as e:
        _log_and_reraise(e, id_cms, "update")
    except Exception as e:  # noqa: BLE001
        log.exception("update_endpoint_unexpected", id_cms=id_cms)
        raise HTTPException(500, "Error interno del microservicio") from e


@router.get("/{id_cms}")
async def get_status(id_cms: str) -> dict:
    try:
        return await service.get_status(id_cms)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except MeliError as e:
        _log_and_reraise(e, id_cms, "get_status")
    except Exception as e:  # noqa: BLE001
        log.exception("get_status_endpoint_unexpected", id_cms=id_cms)
        raise HTTPException(500, "Error interno del microservicio") from e


@router.post("/{id_cms}/upgrade", dependencies=[Depends(verify_webhook)])
async def upgrade(id_cms: str, req: UpgradeListingRequest) -> dict:
    try:
        return await service.upgrade(id_cms, req)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except MeliError as e:
        _log_and_reraise(e, id_cms, "upgrade")
    except Exception as e:  # noqa: BLE001
        log.exception("upgrade_endpoint_unexpected", id_cms=id_cms)
        raise HTTPException(500, "Error interno del microservicio") from e


@router.delete("/{id_cms}", dependencies=[Depends(verify_webhook)])
async def delete(id_cms: str) -> dict:
    try:
        return await service.delete(id_cms)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except MeliError as e:
        _log_and_reraise(e, id_cms, "delete")
    except Exception as e:  # noqa: BLE001
        log.exception("delete_endpoint_unexpected", id_cms=id_cms)
        raise HTTPException(500, "Error interno del microservicio") from e
