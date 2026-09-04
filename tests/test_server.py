"""Серверный слой: открытый реестр, платный поиск, hosted, честные отказы."""

from __future__ import annotations

from dataclasses import replace

import pytest

import mcp_trademarks.server as srv
from mcp_trademarks.errors import BackendError, SourceUnavailable, TrademarksError
from mcp_trademarks.fips_open import FipsOpenError


async def test_search_without_key_is_not_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(
        srv, "_settings", replace(srv._settings, token=None, fips_login=None, fips_password=None)
    )
    out = await srv.search_trademark("Ромашка", None, "all", 20)
    assert out["error"] == "source_not_configured"
    assert out["ready"] is False
    assert "results" not in out
    assert "MCP_TRADEMARKS_FIPS_LOGIN" in out["message_ru"]
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_search_with_fips_login_does_not_invent_exchange(monkeypatch) -> None:
    monkeypatch.setattr(
        srv,
        "_settings",
        replace(srv._settings, token=None, fips_login="user", fips_password="secret"),
    )
    out = await srv.search_trademark("Ромашка", [35], "all", 10)
    assert out["error"] == "spec_closed"
    assert "results" not in out
    assert "не отправляем" in out["message_ru"] or "не отправляю" in out["message_ru"]


async def test_hosted_401_is_invalid_key_not_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        srv, "_settings", replace(srv._settings, token="bad", fips_login=None, fips_password=None)
    )

    async def _boom() -> dict:
        raise BackendError(401, "bad key")

    out = await srv._hosted_call("search_trademark", _boom)
    assert out["error"] == "invalid_credentials"
    assert out.get("found") is not False
    assert out.get("results") is None


async def test_hosted_disclaimer_injected(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k"))

    async def _ok() -> dict:
        return {"ready": False, "source": "hosted"}

    out = await srv._hosted_call("x", _ok)
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_hosted_backend_error_500(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k"))

    async def _boom() -> dict:
        raise BackendError(500, "down")

    out = await srv._hosted_call("search_trademark", _boom)
    assert out["error"] == "backend_error"
    assert out["status"] == 500


async def test_hosted_trademarks_error(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token="k"))

    async def _boom() -> dict:
        raise TrademarksError("offline")

    out = await srv._hosted_call("search_trademark", _boom)
    assert out["error"] == "source_unavailable"


@pytest.fixture
def with_token_and_mock_call(monkeypatch):
    monkeypatch.setattr(
        srv, "_settings", replace(srv._settings, token="k", fips_login=None, fips_password=None)
    )

    async def _mock_call(fn):
        return {"results": [], "source": "fips"}

    monkeypatch.setattr(srv, "_call", _mock_call)


async def test_search_trademark_tool_hosted(with_token_and_mock_call) -> None:
    out = await srv.search_trademark("Ромашка", [43], "all", 20)
    assert out["disclaimer"] == srv.DISCLAIMER
    assert out["source"] == "fips"


async def test_assess_similarity_tool(with_token_and_mock_call) -> None:
    out = await srv.assess_similarity("Кандидат", ["Ромашка"], [35])
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_search_tmview_without_key(monkeypatch) -> None:
    monkeypatch.setattr(srv, "_settings", replace(srv._settings, token=None))
    out = await srv.search_tmview("Brand", [9], ["EM"])
    assert out["error"] == "source_not_configured"
    assert "TMview" in out["source"]


async def test_get_trademark_status_open_card(monkeypatch) -> None:
    class FakeOpen:
        async def get_certificate(self, number: str) -> dict:
            return {"ready": True, "found": True, "number": number, "holder": "ООО Ромашка"}

    async def _fake() -> FakeOpen:
        return FakeOpen()

    monkeypatch.setattr(srv, "_get_fips_open", _fake)
    out = await srv.get_trademark_status("123456")
    assert out["found"] is True
    assert out["disclaimer"] == srv.DISCLAIMER


async def test_get_trademark_status_source_down(monkeypatch) -> None:
    class FakeOpen:
        async def get_certificate(self, number: str) -> dict:
            raise SourceUnavailable("ФИПС не ответил вовремя.")

    async def _fake() -> FakeOpen:
        return FakeOpen()

    monkeypatch.setattr(srv, "_get_fips_open", _fake)
    out = await srv.get_trademark_status("123456")
    assert out["error"] == "source_unavailable"
    assert out.get("found") is not False


async def test_get_trademark_status_bad_number(monkeypatch) -> None:
    class FakeOpen:
        async def get_certificate(self, number: str) -> dict:
            raise FipsOpenError("Номер свидетельства должен быть цифрами")

    async def _fake() -> FakeOpen:
        return FakeOpen()

    monkeypatch.setattr(srv, "_get_fips_open", _fake)
    out = await srv.get_trademark_status("Ромашка")
    assert out["error"] == "invalid_number"


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
