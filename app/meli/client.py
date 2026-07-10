"""Cliente async httpx hacia MELI con Bearer, retry (tenacity) y refresh en 401."""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.auth.meli_oauth import force_refresh, get_valid_access_token
from app.core.config import get_settings
from app.core.logging import get_logger
from app.meli import endpoints as ep
from app.meli.errors import (
    MeliAuthError,
    MeliError,
    MeliRateLimitError,
    classify_error,
    is_retryable,
)

log = get_logger(__name__)


class MeliClient:
    """Cliente thin hacia MELI. Maneja auth y reintentos transparente."""

    def __init__(self, timeout: float | None = None) -> None:
        settings = get_settings()
        self._timeout = timeout or settings.meli_http_timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> MeliClient:
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            http2=True,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None

    async def _headers(self) -> dict[str, str]:
        token = await get_valid_access_token()
        return {"Authorization": f"Bearer {token}"}

    async def _raw_request(self, method: str, url: str, *, json: Any | None = None,
                           params: dict | None = None) -> Any:
        if self._client is None:  # pragma: no cover
            raise RuntimeError("MeliClient no inicializado. Usar 'async with MeliClient() as c:'")
        resp = await self._client.request(
            method, url, json=json, params=params, headers=await self._headers(),
        )
        if resp.status_code == 429:
            raise MeliRateLimitError(429, "rate_limited", body=_safe_body(resp))
        if resp.status_code >= 400:
            raise classify_error(resp.status_code, _safe_body(resp))
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def _with_retry(self, method: str, url: str, *, json: Any | None = None,
                          params: dict | None = None, _allow_auth_retry: bool = True) -> Any:
        # Backoff para 429/500/409 conflictivos
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(MeliRateLimitError),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=20),
            reraise=True,
        ):
            with attempt:
                return await self._raw_request(method, url, json=json, params=params)

    async def call(self, method: str, url: str, *, json: Any | None = None,
                   params: dict | None = None) -> Any:
        try:
            return await self._with_retry(method, url, json=json, params=params)
        except MeliAuthError as e:
            if e.body.get("error") in ("invalid_token", "invalid_grant"):
                log.warning("meli_401_forcing_refresh", error=e.body.get("error"))
                await force_refresh()
                return await self._with_retry(
                    method, url, json=json, params=params, _allow_auth_retry=False
                )
            raise
        except MeliError as e:
            if is_retryable(e) and not isinstance(e, MeliAuthError):
                async for attempt in AsyncRetrying(
                    retry=retry_if_exception_type((MeliError,)),
                    stop=stop_after_attempt(4),
                    wait=wait_exponential(multiplier=2, min=2, max=30),
                    reraise=True,
                ):
                    with attempt:
                        return await self._raw_request(method, url, json=json, params=params)
            raise

    # ───── Atajos para operaciones de inmuebles ─────

    async def publish_item(self, payload: dict) -> dict:
        return await self.call("POST", ep.items(), json=payload)

    async def get_item(self, item_id: str) -> dict:
        return await self.call("GET", ep.item(item_id))

    async def update_item(self, item_id: str, payload: dict) -> dict:
        return await self.call("PUT", ep.item(item_id), json=payload)

    async def delete_item(self, item_id: str) -> None:
        await self.call("DELETE", ep.item(item_id))

    async def change_listing_type(self, item_id: str, listing_type_id: str) -> dict:
        return await self.call("POST", ep.item_listing_type(item_id), json={"id": listing_type_id})

    async def search_user_items(self, user_id: str, *, status: str | None = None) -> dict:
        params = {"status": status} if status else None
        return await self.call("GET", ep.user_items_search(user_id), params=params)

    async def get_category_attributes(self, category_id: str) -> list[dict]:
        return await self.call("GET", ep.category_attributes(category_id))

    async def predict_category(self, site_id: str, title: str) -> list[dict]:
        return await self.call(
            "GET",
            ep.category_predictor(site_id),
            params={"q": title, "limit": "4", "target": "classified"},
        )

    async def get_listing_types(self, site_id: str) -> list[dict]:
        return await self.call("GET", ep.listing_types(site_id))

    async def get_packs(self, user_id: str, listing_type: str, category_id: str) -> dict:
        return await self.call(
            "GET",
            ep.packs_for_user(user_id, listing_type),
            params={"categoryId": category_id},
        )


def _safe_body(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"message": resp.text, "error": "non_json"}
