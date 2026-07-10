"""Renovacion automatica del access_token MELI con refresh_token.

- Lee el refresh_token inicial de MELI_REFRESH_TOKEN env (1a vez).
- Lo persiste en Mongo y rota de ahi en adelante.
- Solo renueva si el access_token esta expirado o vacio.
- Usa asyncio.Lock para evitar doble-refresh concurrente.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.auth.token_store import (
    TokenBundle,
    atomic_rotate,
    get_tokens,
    save_tokens,
    set_bootstrap_refresh_token,
)
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_refresh_lock = asyncio.Lock()


class MeliAuthError(RuntimeError):
    pass


async def _refresh_with_meli(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.meli_http_timeout) as client:
        resp = await client.post(
            settings.meli_auth_url,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.meli_client_id,
                "client_secret": settings.meli_client_secret,
                "refresh_token": refresh_token,
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        log.error("meli_refresh_failed", status=resp.status_code, body=resp.text)
        raise MeliAuthError(f"MELI refresh failed: {resp.status_code} {resp.text}")
    return resp.json()


async def bootstrap() -> None:
    """Llamado desde startup del lifespan: persiste refresh_token inicial si Mongo esta vacio."""
    settings = get_settings()
    await set_bootstrap_refresh_token(settings.meli_refresh_token)
    log.info("auth_bootstrap_ok")


async def get_valid_access_token() -> str:
    """Devuelve un access_token valido. Renueva con refresh si expiro o esta vacio."""
    bundle = await get_tokens()
    if bundle and bundle.access_token and not bundle.is_expired:
        return bundle.access_token

    async with _refresh_lock:
        # Recheck por si otra corutina renovo mientras esperaba el lock.
        bundle = await get_tokens()
        if bundle and bundle.access_token and not bundle.is_expired:
            return bundle.access_token

        if not bundle or not bundle.refresh_token:
            raise MeliAuthError("No hay refresh_token persistido. Verifica MELI_REFRESH_TOKEN env.")

        known_refresh = bundle.refresh_token
        try:
            data = await _refresh_with_meli(known_refresh)
        except MeliAuthError:
            # Revertir a refresh_token del env como fallback (poco comun).
            settings = get_settings()
            if settings.meli_refresh_token and settings.meli_refresh_token != known_refresh:
                data = await _refresh_with_meli(settings.meli_refresh_token)
                known_refresh = settings.meli_refresh_token
            else:
                raise

        new_bundle = await atomic_rotate(
            known_refresh_token=known_refresh,
            new_access_token=data["access_token"],
            new_refresh_token=data["refresh_token"],
            expires_in=int(data["expires_in"]),
        )
        if not new_bundle:
            # Otra corutina gano la rotacion. Lee lo persistido.
            new_bundle = await get_tokens()
            if not new_bundle or not new_bundle.access_token:
                raise MeliAuthError("Rotacion atomica fallo y no hay token legible.")
        log.info("meli_token_refreshed", expires_in=data["expires_in"])
        return new_bundle.access_token


async def force_refresh() -> TokenBundle:
    """Fuerza un refresh inmediato (usado cuando MELI responde 401)."""
    async with _refresh_lock:
        bundle = await get_tokens()
        if not bundle or not bundle.refresh_token:
            raise MeliAuthError("No hay refresh_token para forzar refresh.")
        refresh_token = bundle.refresh_token
        data = await _refresh_with_meli(refresh_token)
        new_bundle = await atomic_rotate(
            known_refresh_token=refresh_token,
            new_access_token=data["access_token"],
            new_refresh_token=data["refresh_token"],
            expires_in=int(data["expires_in"]),
        )
        if not new_bundle:
            new_bundle = await save_tokens(
                data["access_token"], data["refresh_token"], int(data["expires_in"])
            )
        return new_bundle
