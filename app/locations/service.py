"""Helpers de ubicaciones Mexico (MLM).

MELI pide enviar solo el ID de la localidad mas granular disponible
(en Mexico: estado -> municipio/delegacion -> colonia/asentamiento).

Coleccion de IDs base (MLM):
  Pais:           MLM (sitio)
  Estado ejemplo: MLM-MEX-D.F.      (Ciudad de Mexico)
  Ciudad ejemplo: TUxNQ01VTjkxNw      (Mun. de Mexico)
"""
from __future__ import annotations

from app.meli import endpoints as ep
from app.meli.client import MeliClient


async def get_country(country_id: str = "ML") -> dict:
    async with MeliClient() as client:
        return await client.call("GET", ep.classified_locations_countries(country_id))


async def get_state(state_id: str) -> dict:
    async with MeliClient() as client:
        return await client.call("GET", ep.classified_locations_states(state_id))


async def get_city(city_id: str) -> dict:
    async with MeliClient() as client:
        return await client.call("GET", ep.classified_locations_cities(city_id))


async def hide_exact_address(item_id: str) -> None:
    """Oculta la direccion exacta del aviso (por privacidad del vendedor)."""
    async with MeliClient() as client:
        await client.call("PUT", ep.item_address_by_reference(item_id))


async def show_exact_address(item_id: str) -> None:
    """Revierte la ocultacion de direccion exacta."""
    async with MeliClient() as client:
        await client.call("DELETE", ep.item_address_by_reference(item_id))
