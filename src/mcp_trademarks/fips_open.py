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
# 181/186 — срок действия и продление (на живых карточках ФИПС часто вместо 180).
_INID_FIRST = {
    "111": "registration_number",
    "151": "registration_date",
    "210": "application_number",
    "220": "application_date",
    "511": "nice_classes_raw",
    "540": "mark_text",
    "731": "holder",
    "732": "holder",
}
_INID_LAST = {
    "141": "termination_date",
    "180": "expiry_date",
    "181": "expiry_date",
    "186": "expiry_date",
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
_BIB_P_RE = re.compile(r'<p[^>]*class="[^"]*\bbib\b[^"]*"[^>]*>(.*?)</p>', re.I | re.S)
_INID_CELL_RE = re.compile(
    r"\((\d{3})\)[^<]{0,200}?</td>\s*<td[^>]*>(.*?)</td>",
    re.I | re.S,
)
_INID_LINE_RE = re.compile(
    r"\((\d{3})\)[^\n\t]{0,80}[\t:]\s*([^\n<(]{1,400})",
    re.I,
)
_INID_CODE_RE = re.compile(r"\((\d{3})\)")
_IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
_STATUS_RE = re.compile(
    r'class="Status"[^>]*>.*?Статус:\s*([^<(]+)',
    re.I | re.S,
)
_CLASS_LINE_RE = re.compile(r"(?:^|[\s>])(0?[1-9]|[1-3][0-9]|4[0-5])\s*[-–—]")
_NUMBER_RE = re.compile(r"^\d{1,12}$")
_PARSE_FAILED_RU = (
    "Документ с этим номером в открытом реестре ФИПС есть, но поля карточки "
    "разобрать не удалось. Откройте первоисточник и посмотрите глазами. "
    "Это не ответ «знака нет»."
)


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


def _plain_fragment(html: str) -> str:
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", html)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return re.sub(r"\n{2,}", "\n", cleaned).strip()


def _clean_value(raw: str) -> str:
    value = unescape(_TAG_RE.sub(" ", raw))
    value = re.sub(r"\s+", " ", value).strip(" \t.;\n")
    return value


def _value_after_code(plain: str) -> str:
    rest = _INID_CODE_RE.sub("", plain, count=1).strip()
    rest = re.sub(r"^[^:\n]{1,80}:\s*", "", rest, count=1).strip()
    return re.sub(r"\s+", " ", rest).strip(" \t.;")


def _collect_inid(html: str, text: str) -> tuple[dict[str, list[str]], list[str]]:
    values: dict[str, list[str]] = {}
    images: list[str] = []

    def add(code: str, value: str) -> None:
        if code and value:
            values.setdefault(code, []).append(value)

    for block in _BIB_P_RE.findall(html):
        code_m = _INID_CODE_RE.search(block)
        if not code_m:
            continue
        code = code_m.group(1)
        for img in _IMG_SRC_RE.findall(block):
            src = unescape(img.strip())
            if src:
                images.append(src)
        add(code, _value_after_code(_plain_fragment(block)))

    for match in _INID_CELL_RE.finditer(html):
        add(match.group(1), _clean_value(match.group(2)))

    if not values:
        for match in _INID_LINE_RE.finditer(text):
            add(match.group(1), match.group(2).strip(" \t.;"))

    if not images:
        images = [unescape(src) for src in _IMG_SRC_RE.findall(html) if src.strip()]
    return values, images


def _pick(values: dict[str, list[str]], code: str, *, last: bool = False) -> str | None:
    items = values.get(code) or []
    if not items:
        return None
    return items[-1] if last else items[0]


def _nice_classes(raw: str | None) -> list[int]:
    if not raw:
        return []
    seen: list[int] = []
    for match in _CLASS_LINE_RE.finditer(raw):
        num = int(match.group(1))
        if num not in seen:
            seen.append(num)
    if seen:
        return seen
    for match in re.finditer(r"\b([1-9]|[1-3][0-9]|4[0-5])\b", raw):
        num = int(match.group(1))
        if num not in seen:
            seen.append(num)
    return seen


def _normalize_mark_text(value: str | None) -> str | None:
    if not value:
        return None
    folded = value.casefold()
    if folded.startswith("изображение") and len(value) < 90:
        return None
    return value


def _legal_status(html: str, folded: str) -> str | None:
    status_m = _STATUS_RE.search(html)
    if status_m:
        status = re.sub(r"\s+", " ", status_m.group(1)).strip()
        if status:
            return status
    guess = re.search(r"(действует|прекратил(?:а)? действие|аннулирован)", folded)
    return guess.group(1) if guess else None


def _parse_failed(number: str) -> dict[str, Any]:
    return {
        "ready": True,
        "found": None,
        "error": "parse_failed",
        "number": number,
        "source": SOURCE,
        "source_url": None,
        "message_ru": _PARSE_FAILED_RU,
    }


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

    collected, images = _collect_inid(html, text)
    fields: dict[str, str] = {}
    for code, key in _INID_FIRST.items():
        value = _pick(collected, code)
        if value and key not in fields:
            fields[key] = value
    for code, key in _INID_LAST.items():
        value = _pick(collected, code, last=True)
        if value:
            fields[key] = value

    nice_raw = fields.get("nice_classes_raw")
    nice_classes = _nice_classes(nice_raw)
    mark_text = _normalize_mark_text(fields.get("mark_text"))
    mark_image = images[0] if images else None
    holder = fields.get("holder")
    has_document = bool(collected) or bool(_INID_CODE_RE.search(html))
    substantive = bool(holder) and (bool(nice_classes) or bool(mark_text) or bool(mark_image))
    if not substantive:
        if has_document:
            return _parse_failed(number)
        raise SourceUnavailable(
            "Страница открытого реестра ФИПС пришла, но карточки с кодами INID на ней нет. "
            "Не считаем это «знак не найден»."
        )

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
        "holder": holder,
        "mark_text": mark_text,
        "mark_image_url": mark_image,
        "nice_classes": nice_classes or None,
        "nice_classes_raw": nice_raw,
        "legal_status_raw": _legal_status(html, folded),
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
