"""Серверный слой: hosted wrappers, tool paths, client singleton, CLI parser."""

from __future__ import annotations

from dataclasses import replace

import pytest

import mcp_trademarks.server as srv
from mcp_trademarks.errors import BackendError, TrademarksError


async def test_no_token_hint(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token=None))
    out = await srv._hosted_call("x", lambda: _fail())
    assert out["error"] == "missing_token"
    assert "MCP_TRADEMARKS_API_KEY" in out["message_ru"]
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_disclaimer_injected(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k"))

    async def _ok() -> dict:
        return {"results": []}

    out = await srv._hosted_call("x", _ok)
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_hosted_backend_error_500(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k"))

    async def _boom() -> dict:
        raise BackendError(500, "down")

    out = await srv._hosted_call("search_trademark", _boom)
    assert out["error"] == "backend_error"
    assert out["status"] == 500


async def test_hosted_backend_error_401(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k"))

    async def _boom() -> dict:
        raise BackendError(401, "bad key")

    out = await srv._hosted_call("search_trademark", _boom)
    assert out["error"] == "missing_token"


async def test_hosted_trademarks_error(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k"))

    async def _boom() -> dict:
        raise TrademarksError("offline")

    out = await srv._hosted_call("search_trademark", _boom)
    assert out["error"] == "unavailable"


@pytest.fixture
def with_token_and_mock_call(monkeypatch):
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k"))

    async def _mock_call(fn):
        return {"results": [], "source": "fips"}

    monkeypatch.setattr(srv, "_call", _mock_call)


async def test_search_trademark_tool(with_token_and_mock_call) -> None:
    out = await srv.search_trademark("Ромашка", [43], "all", 20)
    assert out["disclaimer"] == srv.DISCLAIMER
    assert out["source"] == "fips"


async def test_assess_similarity_tool(with_token_and_mock_call) -> None:
    out = await srv.assess_similarity("Кандидат", ["Ромашка"], [35])
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_get_trademark_status_tool(with_token_and_mock_call) -> None:
    out = await srv.get_trademark_status("2024712345")
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_search_tmview_tool(with_token_and_mock_call) -> None:
    out = await srv.search_tmview("Brand", [9], ["EM"])
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_get_client_singleton(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_client", None)
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k", api_base="http://test"))

    class FakeClient:
        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(srv, "TrademarksClient", lambda _s: FakeClient())
    first = await srv._get_client()
    second = await srv._get_client()
    assert first is second


def test_build_arg_parser_version() -> None:
    parser = srv._build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--version"])


async def _fail() -> dict:
    raise AssertionError("should not be called without token")
