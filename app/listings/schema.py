"""Schemas Pydantic del JSON que MELI espera en POST /items (inmuebles MLM).

Validacion estricta ANTES de llamar a MELI para evitar 400 evitables.
Documentacion: https://developers.mercadolibre.com.ar/es_ar/publica-inmueble
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

# MELI Mexico (MLM): monedas aceptadas
CurrencyMLM = Literal["MXN", "USD"]

# listing_type_id validos para Inmuebles (la guia: silver/gold/gold_pro)
# NOTA: en MLM el "Oro Premium" es gold_pro, NO gold_premium.
ListingType = Literal["silver", "gold", "gold_pro"]

BuyingMode = Literal["classified"]
Condition = Literal["new", "used", "not_specified"]
Channel = Literal["marketplace", "mshops"]

SiteMLM = Literal["MLM"]


class Picture(BaseModel):
    source: HttpUrl
    # MELI tambien acepta mega xxxx|xxxxx para imagenes subidas; amenos aceptamos URL

    def to_meli(self) -> dict:
        return {"source": str(self.source)}


class SellerContact(BaseModel):
    contact: str
    email: str
    phone: str

    def to_meli(self) -> dict:
        return {"contact": self.contact, "email": self.email, "phone": self.phone}


class MeliLocation(BaseModel):
    # MELI pide que enviemos el ID de la localidad mas granular disponible.
    city_id: str | None = None
    state_id: str | None = None
    neighborhood_id: str | None = None
    country_id: str | None = None
    address_line: str = Field(..., min_length=1, description="Formato: calle + numero (obligatorio jul 2024)")
    latitude: float | None = None
    longitude: float | None = None
    zip_code: str | None = None

    @field_validator("address_line")
    @classmethod
    def _must_have_number(cls, v: str) -> str:
        # Heuristica simple: al menos una palabra y al menos un digito.
        has_digit = any(ch.isdigit() for ch in v)
        if not has_digit:
            raise ValueError(
                "address_line debe seguir el formato 'calle + numero' (jul 2024 - MELI pausa los avisos que no cumplen)"
            )
        return v

    def to_meli(self) -> dict:
        out: dict[str, object] = {"address_line": self.address_line}
        if self.country_id: out["country_id"] = self.country_id
        if self.state_id: out["state_id"] = self.state_id
        if self.city_id: out["city_id"] = self.city_id
        if self.neighborhood_id: out["neighborhood_id"] = {"id": self.neighborhood_id}
        if self.latitude is not None: out["latitude"] = self.latitude
        if self.longitude is not None: out["longitude"] = self.longitude
        if self.zip_code: out["zip_code"] = self.zip_code
        return out


class MeliAttribute(BaseModel):
    id: str
    value_id: str | None = None
    value_name: str | int | float | None = None
    values: list[dict] | None = None  # para atributos complejos

    @model_validator(mode="after")
    def _has_value(self) -> MeliAttribute:
        if self.value_name is None and not self.values:
            raise ValueError(f"attribute '{self.id}' necesita value_name o values")
        return self

    def to_meli(self) -> dict:
        out: dict[str, object] = {"id": self.id}
        if self.value_id: out["value_id"] = self.value_id
        if self.value_name is not None: out["value_name"] = self.value_name
        if self.values: out["values"] = self.values
        return out


class MeliVariation(BaseModel):
    """Unidad de un desarrollo inmobiliario (1 unidad = 1 variacion)."""

    price: float = Field(..., gt=0)
    attribute_combinations: list[MeliAttribute] = Field(default_factory=list)
    picture_ids: list[str] = Field(default_factory=list)
    available_quantity: int = 1
    sku: str | None = None

    def to_meli(self) -> dict:
        out: dict[str, object] = {
            "price": self.price,
            "attribute_combinations": [a.to_meli() for a in self.attribute_combinations],
            "available_quantity": self.available_quantity,
        }
        if self.picture_ids: out["picture_ids"] = self.picture_ids
        if self.sku: out["seller_custom_field"] = self.sku
        return out


class MeliItemCreate(BaseModel):
    """Payload para POST /items (inmueble individual o desarrollo con variaciones)."""

    category_id: str
    title: str = Field(..., min_length=2, max_length=60)
    price: float = Field(..., gt=0)
    currency_id: CurrencyMLM = "MXN"
    available_quantity: Literal[1] = 1  # clasificados siempre 1
    buying_mode: BuyingMode = "classified"
    listing_type_id: ListingType = "silver"
    condition: Condition = "not_specified"
    channels: list[Channel] = ["marketplace"]
    pictures: list[Picture] = Field(..., min_length=1, description="Obligatorio desde feb 2026 (error 173)")
    seller_contact: SellerContact
    location: MeliLocation
    attributes: list[MeliAttribute] = Field(default_factory=list)
    variations: list[MeliVariation] = Field(default_factory=list)
    video_id: str | None = None
    official_store_id: str | None = None
    site_id: SiteMLM = "MLM"  # informativo, MELI lo infiere del category_id

    @field_validator("pictures")
    @classmethod
    def _min1_image(cls, v: list[Picture]) -> list[Picture]:
        # Regla MELI feb 2026: error 173 si no hay imagen (silver+)
        if not v:
            raise ValueError("MELI requiere al menos 1 imagen (regla feb 2026, error 173)")
        return v

    def to_meli(self) -> dict:
        out: dict[str, object] = {
            "category_id": self.category_id,
            "title": self.title,
            "price": self.price,
            "currency_id": self.currency_id,
            "available_quantity": self.available_quantity,
            "buying_mode": self.buying_mode,
            "listing_type_id": self.listing_type_id,
            "condition": self.condition,
            "channels": self.channels,
            "pictures": [p.to_meli() for p in self.pictures],
            "seller_contact": self.seller_contact.to_meli(),
            "location": self.location.to_meli(),
            "attributes": [a.to_meli() for a in self.attributes],
        }
        out["variations"] = [v.to_meli() for v in self.variations]
        if self.video_id: out["video_id"] = self.video_id
        if self.official_store_id: out["official_store_id"] = self.official_store_id
        return out


class MeliItemUpdate(BaseModel):
    """Payload parcial para PUT /items/{id}. Solo los campos editables."""

    title: str | None = Field(default=None, max_length=60)
    price: float | None = Field(default=None, gt=0)
    pictures: list[Picture] | None = None
    seller_contact: SellerContact | None = None
    location: MeliLocation | None = None
    attributes: list[MeliAttribute] | None = None
    variations: list[MeliVariation] | None = None
    video_id: str | None = None
    available_quantity: Literal[1] | None = None

    def to_meli(self) -> dict:
        out: dict[str, object] = {}
        if self.title is not None: out["title"] = self.title
        if self.price is not None: out["price"] = self.price
        if self.pictures is not None: out["pictures"] = [p.to_meli() for p in self.pictures]
        if self.seller_contact is not None: out["seller_contact"] = self.seller_contact.to_meli()
        if self.location is not None: out["location"] = self.location.to_meli()
        if self.attributes is not None: out["attributes"] = [a.to_meli() for a in self.attributes]
        if self.variations is not None: out["variations"] = [v.to_meli() for v in self.variations]
        if self.video_id is not None: out["video_id"] = self.video_id
        if self.available_quantity is not None: out["available_quantity"] = self.available_quantity
        return out


class UpgradeListingRequest(BaseModel):
    listing_type_id: ListingType

    @field_validator("listing_type_id")
    @classmethod
    def _no_gold_premium(cls, v: str) -> str:
        # Anti-pie: la guia advierte que gold_premium NO existe en MLM. Es gold_pro.
        if v == "gold_premium":  # pragma: no cover - Literal ya lo filtra, defensive
            raise ValueError("Usar gold_pro (Oro Premium) en MLM, no gold_premium")
        return v


# ───── DTOs que el CMS envia via webhook ─────────────────────────────

class CmsWebhookPayload(BaseModel):
    """Estructura flexible: el CMS puede mandar el JSON ya formateado para MELI
    o datos propios que el builder transformara. Aceptamos ambos.
    """

    id_cms: str = Field(..., description="ID del inmueble en el CMS")
    tipo: Literal["inmueble", "desarrollo"] = "inmueble"
    meli_payload: MeliItemCreate
    # En el futuro el CMS podria enviar campos crudos; agregalos aqui.
