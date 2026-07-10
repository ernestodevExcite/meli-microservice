"""App FastAPI: lifespan (Mongo+auth bootstrap) y routers."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.meli_oauth import bootstrap as auth_bootstrap
from app.core.config import get_settings
from app.core.db import connect, disconnect
from app.core.logging import configure_logging, get_logger
from app.health.router import router as health_router
from app.listings.router import router as listings_router
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


def create_app() -> FastAPI:
    app = FastAPI(
        title="MELI Bridge - CMS <-> Mercado Libre Inmuebles (MLM)",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.include_router(health_router)
    app.include_router(listings_router)
    app.include_router(notifications_router)
    return app


app = create_app()
