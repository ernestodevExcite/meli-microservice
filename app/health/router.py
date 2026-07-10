"""Healthchecks para Cloud Run: /healthz (liveness) y /readyz (readiness)."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.db import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness: el proceso responde. No verifica dependencias."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    """Readiness: Mongo responde. Cloud Run rutea trafico solo cuando readyz==200."""
    try:
        await get_db().command("ping")
    except Exception as e:  # noqa: BLE001
        return {"status": "not_ready", "error": str(e)}
    return {"status": "ready"}
