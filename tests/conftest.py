"""Fixtures: settings envars (no Mongo real, no llamadas a MELI) y cliente TestClient."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

# Asegurar variables antes de importar app (Settings se evalua al importar).
os.environ.setdefault("MELI_CLIENT_ID", "test_app_id")
os.environ.setdefault("MELI_CLIENT_SECRET", "test_secret")
os.environ.setdefault("MELI_REFRESH_TOKEN", "test_refresh_initial")
os.environ.setdefault("MELI_SITE_ID", "MLM")
os.environ.setdefault("MELI_USER_ID", "1234567890")
# Mongo apuntando a ninguna parte ('\u0000' fuerza error rapido si se usa)
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # Evitamos el lifespan real (que conectaria Mongo y haria bootstrap auth).
    # Para tests de routing basta con la app sin startup.
    from app.main import create_app

    app = create_app()
    # Removemos el lifespan para no tocar Mongo en tests.
    app.router.lifespan_context = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
