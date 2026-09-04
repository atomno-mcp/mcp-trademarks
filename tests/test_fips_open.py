"""Открытый реестр ФИПС: разбор карточки, «нет документа», сбои источника (моки)."""

from __future__ import annotations

import httpx
import pytest
import respx

from mcp_trademarks.errors import SourceUnavailable
from mcp_trademarks.fips_open import (
    DEFAULT_FIPS_OPEN_BASE,
    FipsOpenClient,
    FipsOpenError,
    normalize_certificate_number,
    parse_open_card,
)

CARD_HTML = """<!DOCTYPE HTML>
<html><head><meta charset="windows-1251"><title>RUTM 123456</title></head>
<body>
<table>
<tr><td>(111) Номер регистрации</td><td>123456</td></tr>
<tr><td>(210) Номер заявки</td><td>2014712345</td></tr>
<tr><td>(220) Дата подачи заявки</td><td>15.03.2014</td></tr>
<tr><td>(151) Дата регистрации</td><td>20.01.2015</td></tr>
<tr><td>(180) Дата истечения срока действия регистрации</td><td>15.03.2024</td></tr>
<tr><td>(732) Правообладатель</td><td>Общество с ограниченной ответственностью «Ромашка»</td></tr>
<tr><td>(511) Классы МКТУ и перечень товаров и/или услуг</td><td>35, 41</td></tr>
<tr><td>(540) Изображение товарного знака</td><td>РОМАШКА</td></tr>
</table>
<p>Статус: действует</p>
</body></html>
"""

NOT_FOUND_HTML = "Документ с данным номером отсутствует"
REJECTED_HTML = "<p>Запрос данного документа отклонен.</p>"


def test_normalize_digits_and_ru_prefix() -> None:
    assert normalize_certificate_number("00123456") == "123456"
    assert normalize_certificate_number("RU 123456") == "123456"


def test_normalize_rejects_name() -> None:
    with pytest.raises(FipsOpenError):
        normalize_certificate_number("Ромашка")


def test_parse_card_extracts_inid() -> None:
    card = parse_open_card(CARD_HTML, number="123456")
    assert card["found"] is True
    assert card["ready"] is True
    assert card["holder"] and "Ромашка" in card["holder"]
    assert card["nice_classes"] == [35, 41]
    assert card["mark_text"] == "РОМАШКА"
    assert card["registration_date"] == "20.01.2015"


def test_parse_not_found_is_found_false() -> None:
    card = parse_open_card(NOT_FOUND_HTML, number="1")
    assert card["found"] is False
    assert card["ready"] is True
    assert "нет документа" in card["message_ru"]


def test_parse_rejected_is_not_empty_list() -> None:
    with pytest.raises(SourceUnavailable):
        parse_open_card(REJECTED_HTML, number="100")


@respx.mock
async def test_get_certificate_happy() -> None:
    url = f"{DEFAULT_FIPS_OPEN_BASE}?DB=RUTM&DocNumber=123456&TypeFile=html"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            content=CARD_HTML.encode("cp1251", errors="replace"),
            headers={"content-type": "text/html;charset=windows-1251"},
        )
    )
    client = FipsOpenClient()
    try:
        out = await client.get_certificate("123456")
        assert out["found"] is True
        assert out["source_url"] == url
    finally:
        await client.aclose()


@respx.mock
async def test_get_certificate_not_found() -> None:
    url = f"{DEFAULT_FIPS_OPEN_BASE}?DB=RUTM&DocNumber=1&TypeFile=html"
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            content=NOT_FOUND_HTML.encode("cp1251"),
            headers={"content-type": "text/html;charset=windows-1251"},
        )
    )
    client = FipsOpenClient()
    try:
        out = await client.get_certificate("1")
        assert out["found"] is False
        assert out.get("error") is None
    finally:
        await client.aclose()


@respx.mock
async def test_get_certificate_429_is_unavailable() -> None:
    url = f"{DEFAULT_FIPS_OPEN_BASE}?DB=RUTM&DocNumber=2&TypeFile=html"
    respx.get(url).mock(return_value=httpx.Response(429, text="DDoS-Guard"))
    client = FipsOpenClient()
    try:
        with pytest.raises(SourceUnavailable, match="429"):
            await client.get_certificate("2")
    finally:
        await client.aclose()


@respx.mock
async def test_get_certificate_timeout() -> None:
    url = f"{DEFAULT_FIPS_OPEN_BASE}?DB=RUTM&DocNumber=3&TypeFile=html"
    respx.get(url).mock(side_effect=httpx.TimeoutException("slow"))
    client = FipsOpenClient()
    try:
        with pytest.raises(SourceUnavailable, match="вовремя"):
            await client.get_certificate("3")
    finally:
        await client.aclose()
