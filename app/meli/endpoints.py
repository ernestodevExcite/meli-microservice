"""Constantes de endpoints MELI Inmuebles (MLM)."""
from __future__ import annotations

from urllib.parse import urljoin


def _base() -> str:
    from app.core.config import get_settings
    return get_settings().meli_api_base_url.rstrip("/") + "/"


def oauth_token() -> str:
    from app.core.config import get_settings
    return get_settings().meli_auth_url


def items() -> str:
    return urljoin(_base(), "items")


def item(item_id: str) -> str:
    return urljoin(_base(), f"items/{item_id}")


def item_listing_type(item_id: str) -> str:
    return urljoin(_base(), f"items/{item_id}/listing_type")


def item_address_by_reference(item_id: str) -> str:
    return urljoin(_base(), f"items/{item_id}/address_line_by_reference")


def sites_categories(site_id: str) -> str:
    return urljoin(_base(), f"sites/{site_id}/categories")


def category_attributes(category_id: str) -> str:
    return urljoin(_base(), f"categories/{category_id}/attributes")


def category_predictor(site_id: str) -> str:
    return urljoin(_base(), f"sites/{site_id}/domain_discovery/search")


def classified_locations_countries(country_id: str) -> str:
    return urljoin(_base(), f"classified_locations/countries/{country_id}")


def classified_locations_states(state_id: str) -> str:
    return urljoin(_base(), f"classified_locations/states/{state_id}")


def classified_locations_cities(city_id: str) -> str:
    return urljoin(_base(), f"classified_locations/cities/{city_id}")


def user_items_search(user_id: str) -> str:
    return urljoin(_base(), f"users/{user_id}/items/search")


def listing_types(site_id: str) -> str:
    return urljoin(_base(), f"sites/{site_id}/listing_types")


def packs_for_user(user_id: str, listing_type: str) -> str:
    return urljoin(_base(), f"users/{user_id}/classifieds_promotion_packs/{listing_type}")


def packs_for_category(category_id: str) -> str:
    return urljoin(_base(), f"categories/{category_id}/classifieds_promotion_packs")
