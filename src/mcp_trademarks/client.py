"""HTTP-клиент к hosted-бэкенду trademarks (api.atomno-mcp.ru/trademarks).

Тонкая обёртка над httpx: один общий AsyncClient, заголовок X-API-Key, маппинг
ошибок в TrademarksError. Никакой бизнес-логики (движок сходства и доступ к
реестрам — на приватном сервере). ПДн третьих лиц на нашей стороне не персистятся.
"""

from __future__ import annotations

from typing import Any

import httpx

from . import __version__
from .config import Settings
from .errors import BackendError, BackendUnavailable

_USER_AGENT = f"atomno-mcp-trademarks/{__version__}"


class TrademarksClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        if settings.token:
            headers["X-API-Key"] = settings.token
        self._client = httpx.AsyncClient(
            base_url=settings.api_base,
            timeout=settings.timeout,
            headers=headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise BackendUnavailable(f"timeout calling {path}") from exc
        except httpx.HTTPError as exc:
            raise BackendUnavailable(f"network error calling {path}: {exc}") from exc
        return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code >= 400:
            raise BackendError(resp.status_code, _extract_detail(resp))
        try:
            return resp.json()
        except ValueError as exc:
            raise BackendError(resp.status_code, "invalid JSON in response") from exc

    async def search(
        self,
        query: str,
        classes: list[int] | None,
        status_filter: str,
        limit: int,
    ) -> dict[str, Any]:
        return await self._post(
            "/v1/search",
            {"query": query, "classes": classes, "status_filter": status_filter, "limit": limit},
        )

    async def assess(
        self,
        candidate: str,
        against: list[str] | None,
        classes: list[int] | None,
    ) -> dict[str, Any]:
        return await self._post(
            "/v1/assess", {"candidate": candidate, "against": against, "classes": classes}
        )

    async def status(self, number: str) -> dict[str, Any]:
        return await self._post("/v1/status", {"number": number})

    async def tmview(
        self,
        query: str,
        classes: list[int] | None,
        territories: list[str] | None,
    ) -> dict[str, Any]:
        return await self._post(
            "/v1/tmview", {"query": query, "classes": classes, "territories": territories}
        )


def _extract_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300] or resp.reason_phrase
    if isinstance(body, dict):
        for key in ("message_ru", "detail", "message", "error"):
            if body.get(key):
                return str(body[key])
    return str(body)[:300]
