"""Configuracion central via variables de entorno (pydantic-settings)."""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # MELI OAuth (solo flujo refresh)
    meli_client_id: str = Field(alias="MELI_CLIENT_ID")
    meli_client_secret: str = Field(alias="MELI_CLIENT_SECRET")
    meli_refresh_token: str = Field(alias="MELI_REFRESH_TOKEN")
    meli_redirect_uri: str = Field(alias="MELI_REDIRECT_URI", default="")

    # Cuenta / sitio
    meli_site_id: str = Field(alias="MELI_SITE_ID", default="MLM")
    meli_user_id: str = Field(alias="MELI_USER_ID")

    # URLs base
    meli_api_base_url: str = Field(alias="MELI_API_BASE_URL", default="https://api.mercadolibre.com")
    meli_auth_url: str = Field(alias="MELI_AUTH_URL", default="https://api.mercadolibre.com/oauth/token")

    # Mongo
    mongo_uri: str = Field(alias="MONGO_URI", default="mongodb://mongo:27017")
    mongo_db: str = Field(alias="MONGO_DB", default="meli_bridge")

    # App
    log_level: str = Field(alias="LOG_LEVEL", default="INFO")
    env: str = Field(alias="ENV", default="local")
    webhook_secret: str = Field(alias="WEBHOOK_SECRET", default="")
    meli_http_timeout: float = Field(alias="MELI_HTTP_TIMEOUT", default=20.0)

    @field_validator("meli_site_id")
    @classmethod
    def _upper_site(cls, v: str) -> str:
        return v.upper()

    @property
    def is_prod(self) -> bool:
        return self.env.lower() == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
