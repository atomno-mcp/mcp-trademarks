"""HTTP-клиент к hosted-бэкенду: happy path, 4xx/5xx, таймаут (respx-моки)."""

from __future__ import annotations

import httpx
import pytest
import respx

from mcp_trademarks.client import TrademarksClient
from mcp_trademarks.config import Settings
from mcp_trademarks.errors import BackendError, BackendUnavailable

BASE = "http://test/trademarks"


def _client() -> TrademarksClient:
    return TrademarksClient(Settings(api_base=BASE, token="k", timeout=5.0))


@respx.mock
async def test_search_happy_path() -> None:
    respx.post(f"{BASE}/v1/search").mock(
        return_value=httpx.Response(200, json={"results": [{"number": "123", "designation": "Ромашка"}], "source": "fips"})
    )
    c = _client()
    try:
        out = await c.search("Ромашка", [43, 30], "all", 20)
        assert out["results"][0]["designation"] == "Ромашка"
        assert out["source"] == "fips"
    finally:
        await c.aclose()


@respx.mock
async def test_status_sends_number() -> None:
    route = respx.post(f"{BASE}/v1/status").mock(return_value=httpx.Response(200, json={"status": "registered"}))
    c = _client()
    try:
        out = await c.status("2024712345")
        assert out["status"] == "registered"
        assert route.calls.last.request.read() == b'{"number": "2024712345"}' or b"2024712345" in route.calls.last.request.read()
    finally:
        await c.aclose()


@respx.mock
async def test_backend_401() -> None:
    respx.post(f"{BASE}/v1/assess").mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
    c = _client()
    try:
        with pytest.raises(BackendError) as ei:
            await c.assess("Ромашка", None, None)
        assert ei.value.status_code == 401
    finally:
        await c.aclose()


@respx.mock
async def test_backend_500() -> None:
    respx.post(f"{BASE}/v1/search").mock(return_value=httpx.Response(500, text="boom"))
    c = _client()
    try:
        with pytest.raises(BackendError) as ei:
            await c.search("X", None, "all", 5)
        assert ei.value.status_code == 500
    finally:
        await c.aclose()


@respx.mock
async def test_timeout() -> None:
    respx.post(f"{BASE}/v1/tmview").mock(side_effect=httpx.TimeoutException("slow"))
    c = _client()
    try:
        with pytest.raises(BackendUnavailable):
            await c.tmview("X", None, None)
    finally:
        await c.aclose()
