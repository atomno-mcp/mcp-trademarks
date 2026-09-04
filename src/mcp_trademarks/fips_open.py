"""Карточка товарного знака из открытого реестра ФИПС по номеру свидетельства.

Официальный канал: сервлет открытых реестров, параметр DB=RUTM, поиск только
по номеру документа (так написано на странице открытых реестров ФИПС).
Защиту источника не обходим: при 429/блокировке отвечаем, что источник
недоступен, а не «знака нет».
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any

import httpx

from . import __version__
from .errors import SourceUnavailable, TrademarksError

DEFAULT_FIPS_OPEN_BASE = "https://www1.fips.ru/registers-doc-view/fips_servlet"
OPEN_DB = "RUTM"
SOURCE = "ФИПС, открытые реестры (RUTM), карточка по номеру свидетельства"

# Коды INID для знаков — стандарт ВОИС ST.60, ими размечены карточки открытого реестра.
_INID_FIELDS = {
    "111": "registration_number",
    "141": "termination_date",
    "151": "registration_date",
    "180": "expiry_date",
    "210": "application_number",
    "220": "application_date",
    "511": "nice_classes_raw",
    "540": "mark_text",
    "731": "holder",
    "732": "holder",
}

_NOT_FOUND_MARKERS = (
    "документ с данным номером отсутствует",
    "документ с указанным номером отсутствует",
)
_REJECTED_MARKERS = (
    "запрос данного документа отклонен",
    "запрос данного документа отклонён",
)
_TAG_RE = re.compile(r"<[^>]+>", re.I)
_INID_CELL_RE = re.compile(
    r"\((\d{3})\)[^<]{0,200}?</td>\s*<td[^>]*>(.*?)</td>",
    re.I | re.S,
)
_INID_LINE_RE = re.compile(
    r"\((\d{3})\)[^\n\t]{0,80}[\t:]\s*([^\n<(]{1,400})",
    re.I,
)
_NUMBER_RE = re.compile(r"^\d{1,12}$")


class FipsOpenError(TrademarksError):
    """Ошибка разбора или вызова открытого реестра."""


def normalize_certificate_number(raw: str) -> str:
    number = raw.strip().replace(" ", "").replace("\u00a0", "")
    if number.upper().startswith("RU"):
        number = number[2:]
    if not _NUMBER_RE.match(number):
        raise FipsOpenError(
            "Номер свидетельства должен быть цифрами (допускается префикс RU). "
            "Поиск по названию в открытом реестре не предусмотрен."
        )
    return number.lstrip("0") or "0"


def _decode_body(resp: httpx.Response) -> str:
    charset = (resp.charset_encoding or "").lower()
    raw = resp.content
    if charset in {"windows-1251", "cp1251"}:
        return raw.decode("cp1251", errors="replace")
    for enc in ("cp1251", "utf-8"):
        try:
            text = raw.decode(enc)
            if "�" not in text[:200] or enc == "utf-8":
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1251", errors="replace")


def _plain_text(html: str) -> str:
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", html)
    cleaned = re.sub(r"(?i)</(p|tr|div|li|h[1-6])>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</td>", "\t", cleaned)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cleaned


def parse_open_card(html: str, *, number: str) -> dict[str, Any]:
    """Разобрать HTML карточки открытого реестра. Только поля с кодом INID."""
    text = _plain_text(html)
    folded = text.casefold()
    if any(marker in folded for marker in _NOT_FOUND_MARKERS):
        return {
            "ready": True,
            "found": False,
            "number": number,
            "source": SOURCE,
            "message_ru": "В открытом реестре ФИПС нет документа с этим номером свидетельства.",
        }
    if any(marker in folded for marker in _REJECTED_MARKERS):
        raise SourceUnavailable(
            "ФИПС отклонил выдачу карточки (служебный отказ источника). "
            "Это не ответ «знака нет»."
        )

    fields: dict[str, str] = {}
    for match in _INID_CELL_RE.finditer(html):
        key = _INID_FIELDS.get(match.group(1))
        value = unescape(_TAG_RE.sub(" ", match.group(2))).strip(" \t.;\n")
        value = re.sub(r"\s+", " ", value)
        if key and value:
            fields[key] = value
    if not fields:
        for match in _INID_LINE_RE.finditer(text):
            key = _INID_FIELDS.get(match.group(1))
            value = match.group(2).strip(" \t.;")
            if key and value:
                fields[key] = value

    if not fields:
        raise SourceUnavailable(
            "Страница открытого реестра ФИПС пришла, но карточки с кодами INID на ней нет. "
            "Не считаем это «знак не найден»."
        )

    nice_raw = fields.get("nice_classes_raw")
    nice_classes: list[int] = []
    if nice_raw:
        nice_classes = [int(x) for x in re.findall(r"\b([1-9]|[1-3][0-9]|4[0-5])\b", nice_raw)]

    status_guess = None
    status_match = re.search(r"(действует|прекратил(?:а)? действие|аннулирован)", folded)
    if status_match:
        status_guess = status_match.group(1)

    return {
        "ready": True,
        "found": True,
        "number": number,
        "registration_number": fields.get("registration_number") or number,
        "application_number": fields.get("application_number"),
        "application_date": fields.get("application_date"),
        "registration_date": fields.get("registration_date"),
        "expiry_date": fields.get("expiry_date"),
        "termination_date": fields.get("termination_date"),
        "holder": fields.get("holder"),
        "mark_text": fields.get("mark_text"),
        "nice_classes": nice_classes or None,
        "nice_classes_raw": nice_raw,
        "legal_status_raw": status_guess,
        "source": SOURCE,
        "source_url": None,
        "message_ru": "Карточка из открытого реестра ФИПС по номеру свидетельства.",
    }


class FipsOpenClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_FIPS_OPEN_BASE,
        timeout: float = 30.0,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._http = http
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self._timeout,
                headers={
                    "User-Agent": f"atomno-mcp-trademarks/{__version__}",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
        return self._http

    def card_url(self, number: str) -> str:
        return (
            f"{self._base_url}?DB={OPEN_DB}&DocNumber={number}&TypeFile=html"
        )

    async def get_certificate(self, raw_number: str) -> dict[str, Any]:
        number = normalize_certificate_number(raw_number)
        url = self.card_url(number)
        client = await self._client()
        try:
            resp = await client.get(url)
        except httpx.TimeoutException as exc:
            raise SourceUnavailable(
                "Открытый реестр ФИПС не ответил вовремя."
            ) from exc
        except httpx.HTTPError as exc:
            raise SourceUnavailable(
                f"Открытый реестр ФИПС недоступен: {exc}"
            ) from exc

        if resp.status_code in {401, 403}:
            raise SourceUnavailable(
                f"Открытый реестр ФИПС отклонил запрос (HTTP {resp.status_code}). "
                "Это не ответ «знака нет»."
            )
        if resp.status_code == 429:
            raise SourceUnavailable(
                "Открытый реестр ФИПС ограничил частоту запросов (HTTP 429). "
                "Повторите позже. Это не ответ «знака нет»."
            )
        if resp.status_code >= 500:
            raise SourceUnavailable(
                f"Открытый реестр ФИПС ответил {resp.status_code}."
            )
        if resp.status_code >= 400:
            raise SourceUnavailable(
                f"Открытый реестр ФИПС ответил {resp.status_code}."
            )

        html = _decode_body(resp)
        card = parse_open_card(html, number=number)
        card["source_url"] = url
        return card
