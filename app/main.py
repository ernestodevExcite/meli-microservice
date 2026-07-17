"""App FastAPI: lifespan (Mongo+auth bootstrap) y routers."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth.meli_oauth import bootstrap as auth_bootstrap
from app.core.config import get_settings
from app.core.db import connect, disconnect
from app.core.logging import configure_logging, get_logger
from app.health.router import router as health_router
from app.listings.router import router as listings_router
from app.meli.errors import MeliError, error_body, http_status_for
from app.notifications.router import router as notifications_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    log.info("startup", env=settings.env, site=settings.meli_site_id, user_id=settings.meli_user_id)
    await connect()
    await auth_bootstrap()
    log.info("ready")
    yield
    await disconnect()
    log.info("shutdown")


async def _meli_exception_handler(_: Request, exc: MeliError) -> JSONResponse:
    """Traduce un MeliError a una respuesta HTTP con status honesto.

    - 4xx de negocio MELI (validacion, cuota, not_found, conflict...) -> 4xx.
    - 5xx de MELI (o transitorios que agotaron retry) -> 502 Bad Gateway.
    El logging de contexto (id_cms/op) lo hace cada endpoint en su catch;
    aqui solo logueamos el evento de traduccion para trazabilidad.
    """
    http_status = http_status_for(exc)
    if http_status >= 500:
        log.warning("meli_upstream_error_translated", meli_status=exc.status_code, http_status=http_status)
    return JSONResponse(status_code=http_status, content=error_body(exc))


def create_app() -> FastAPI:
    app = FastAPI(
        title="MELI Bridge - CMS <-> Mercado Libre Inmuebles (MLM)",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_exception_handler(MeliError, _meli_exception_handler)
    app.include_router(health_router)
    app.include_router(listings_router)
    app.include_router(notifications_router)
    return app


app = create_app()
