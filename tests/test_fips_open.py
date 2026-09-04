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

# Живая вёрстка открытого реестра: поля в <p class="bib">, срок в (181)/(186),
# (540) может быть картинкой без словесного элемента.
LIVE_BIB_HTML = """<!DOCTYPE HTML><html><body>
<tr class="Status"><td class="Green">Статус: действует (последнее изменение статуса: 23.11.2003)</td></tr>
<p class="bib">(111) <i>Номер регистрации: </i><b>225163</b></p>
<p class="bib">(210) <i>Номер заявки: </i><b>2000734468</b></p>
<p class="bib">(181) <i>Дата истечения срока действия регистрации: </i><b>28.12.2010</b></p>
<p class="bib">(220) <i>Дата подачи заявки: </i><b>28.12.2000</b></p>
<p class="bib">(151) <i>Дата регистрации: </i><b>17.10.2002</b></p>
<p class="bib">(540)<br><br>
<a href="https://fips.ru/Archive/TM/example.JPG"><img src="https://fips.ru/Archive/TM/example-m.JPG"></a>
</p>
<p class="bib">(732) <i>Имя правообладателя: </i><br>
<b>Общество с ограниченной ответственностью "ЯНДЕКС" Москва (RU)</b></p>
<p class="bib">(511) <i>Классы МКТУ и перечень товаров и/или услуг:</i><br>
<b>35 - реклама; 42 - научные и технологические услуги.</b></p>
<p class="bib">(186) <i>Дата, до которой продлен срок действия регистрации: </i><b>28.12.2030</b></p>
</body></html>
"""

ONLY_NUMBER_HTML = """<table>
<tr><td>(111) Номер регистрации</td><td>225163</td></tr>
</table>
"""

VERBAL_BIB_HTML = """
<p class="bib">(111) <i>Номер регистрации: </i><b>859304</b></p>
<p class="bib">(540) <i>Изображение: </i><b>КОФЕМАНИЯ</b></p>
<p class="bib">(732) <i>Правообладатель: </i><b>ООО «Ромашка»</b></p>
<p class="bib">(511) <i>Классы:</i><br><b>43 - услуги по обеспечению пищевыми продуктами и напитками.</b></p>
"""


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


def test_parse_live_bib_card() -> None:
    card = parse_open_card(LIVE_BIB_HTML, number="225163")
    assert card["found"] is True
    assert card.get("error") is None
    assert "ЯНДЕКС" in (card["holder"] or "")
    assert card["nice_classes"] == [35, 42]
    assert card["expiry_date"] == "28.12.2030"
    assert card["mark_text"] is None
    assert card["mark_image_url"] and "example-m.JPG" in card["mark_image_url"]
    assert card["legal_status_raw"] and "действует" in card["legal_status_raw"]


def test_parse_verbal_mark_text() -> None:
    card = parse_open_card(VERBAL_BIB_HTML, number="859304")
    assert card["found"] is True
    assert card["mark_text"] == "КОФЕМАНИЯ"
    assert card["holder"] == "ООО «Ромашка»"
    assert card["nice_classes"] == [43]


def test_parse_540_label_is_not_mark_text() -> None:
    html = (
        '<p class="bib">(111) <i>Номер: </i><b>1</b></p>'
        '<p class="bib">(540) <i>Изображение товарного знака, знака обслуживания</i>'
        '<img src="https://fips.ru/x.jpg"></p>'
        '<p class="bib">(732) <i>Правообладатель: </i><b>ООО «Ромашка»</b></p>'
        '<p class="bib">(511) <i>Классы:</i><br><b>35 - реклама.</b></p>'
    )
    card = parse_open_card(html, number="1")
    assert card["found"] is True
    assert card["mark_text"] is None
    assert card["mark_image_url"]


def test_parse_number_only_is_parse_failed_not_found() -> None:
    card = parse_open_card(ONLY_NUMBER_HTML, number="225163")
    assert card["found"] is None
    assert card["error"] == "parse_failed"
    assert card["ready"] is True
    assert "первоисточник" in card["message_ru"]


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
