"""Persistencia del par access_token/refresh_token en Mongo (singleton).

MELI rota el refresh_token en cada renovacion (uso unico).
Implementamos update atomico con findAndModify para evitar race conditions
cuando dos requests disparan refresh concurrentemente.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.db import get_db

COLLECTION = "tokens"
SINGLETON_ID = "meli_account"

# Margen de seguridad: renovamos 60s antes de la expiracion real.
SAFETY_MARGIN = timedelta(seconds=60)


class TokenBundle:
    __slots__ = ("access_token", "refresh_token", "expires_at")

    def __init__(self, access_token: str, refresh_token: str, expires_at: datetime) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at


async def save_tokens(access_token: str, refresh_token: str, expires_in: int) -> TokenBundle:
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) - SAFETY_MARGIN
    db = get_db()
    await db[COLLECTION].update_one(
        {"_id": SINGLETON_ID},
        {
            "$set": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "updated_at": datetime.now(UTC),
            }
        },
        upsert=True,
    )
    return TokenBundle(access_token, refresh_token, expires_at)


async def get_tokens() -> TokenBundle | None:
    db = get_db()
    doc = await db[COLLECTION].find_one({"_id": SINGLETON_ID})
    if not doc:
        return None
    return TokenBundle(
        access_token=doc["access_token"],
        refresh_token=doc["refresh_token"],
        expires_at=doc["expires_at"],
    )


async def set_bootstrap_refresh_token(refresh_token: str) -> None:
    """Persiste el refresh_token inicial tomado de variable de entorno.

    Solo se llama si Mongo aun no tiene tokens (primer arranque).
    """
    db = get_db()
    await db[COLLECTION].update_one(
        {"_id": SINGLETON_ID, "refresh_token": {"$exists": False}},
        {
            "$setOnInsert": {
                "access_token": "",
                "refresh_token": refresh_token,
                "expires_at": datetime(2000, 1, 1, tzinfo=UTC),
                "created_at": datetime.now(UTC),
            }
        },
        upsert=True,
    )


async def atomic_rotate(
    known_refresh_token: str,
    new_access_token: str,
    new_refresh_token: str,
    expires_in: int,
) -> TokenBundle | None:
    """Rotacion atomica: solo actualiza si el refresh_token coincide.

    Previene que dos coroutines que vencieron token al mismo tiempo
    persistan tokens distintos. La primera gana, la segunda descarta.
    """
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) - SAFETY_MARGIN
    db = get_db()
    result = await db[COLLECTION].find_one_and_update(
        {"_id": SINGLETON_ID, "refresh_token": known_refresh_token},
        {
            "$set": {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_at": expires_at,
                "updated_at": datetime.now(UTC),
            }
        },
        return_document=True,
    )
    if not result:
        return None
    return TokenBundle(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        expires_at=result["expires_at"],
    )
