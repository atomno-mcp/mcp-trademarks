"""FastMCP entrypoint для atomno-mcp-trademarks.

Карточка по номеру свидетельства — из открытого реестра ФИПС, без ключа.
Поиск по названию у ФИПС платный: без учётки — честный отказ; учётка есть,
но машиночитаемого описания обмена в открытом доступе нет — запрос не шлём.
Оценка сходства справочная, не гарантия регистрации/отказа.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import logging
import os
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from . import __version__
from .client import TrademarksClient
from .config import Settings
from .errors import BackendError, SourceUnavailable, TrademarksError
from .fips_open import FipsOpenClient, FipsOpenError
from .honesty import (
    SOURCE_OPEN,
    SOURCE_PAID,
    SOURCE_TMVIEW,
    invalid_credentials,
    source_not_configured,
    source_unavailable,
    spec_closed,
)

logger = logging.getLogger("mcp_trademarks")

_SUPPORTED_TRANSPORTS = ("stdio", "http", "sse", "streamable-http")
_DEFAULT_TRANSPORT = "stdio"
_DEFAULT_HTTP_HOST = "127.0.0.1"
_DEFAULT_HTTP_PORT = 8000
_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

DISCLAIMER = (
    "Оценка носит справочный характер и не является гарантией регистрации или "
    "отказа в регистрации товарного знака. Инструмент не заменяет патентного "
    "поверенного; окончательное решение принимает специалист. "
    "Не аффилировано с Роспатентом/ФИПС."
)

mcp: FastMCP = FastMCP(
    name="atomno-mcp-trademarks",
    instructions=(
        "Russian trademark MCP. get_trademark_status reads the official FIPS "
        "open register by certificate number — no key. search_trademark is a "
        "paid FIPS search: without the client's FIPS login it refuses honestly; "
        "with login the machine API spec is not public, so we do not invent "
        "the request. Do not treat source_not_configured or spec_closed as "
        "«no trademarks found». We do not have our own FIPS contract; live "
        "paid search has not been verified. Advisory only."
    ),
)

_client: TrademarksClient | None = None
_fips_open: FipsOpenClient | None = None
_client_lock = asyncio.Lock()
_settings = Settings.from_env()

_PAID_SEARCH_HELP = (
    "Поиск по названию у ФИПС платный (информационно-поисковая система, "
    "договор-оферта). Задайте MCP_TRADEMARKS_FIPS_LOGIN и "
    "MCP_TRADEMARKS_FIPS_PASSWORD из своего договора с ФИПС. "
    "Своего доступа к платному поиску ФИПС у нас нет. "
    "Карточка по номеру свидетельства (get_trademark_status) ключа не требует. "
    "Наше размещение — отдельная услуга: MCP_TRADEMARKS_API_KEY."
)

_SPEC_CLOSED_HELP = (
    "Учётка платного поиска ФИПС задана, но машиночитаемого описания обмена "
    "в открытом доступе нет: ИПС — веб-форма, не опубликованный программный "
    "интерфейс. Запрос по догадке не отправляем — это сломает ваш договор. "
    "Когда появится официальное описание методов, поиск включится. "
    "На живом ключе платный поиск не проверяли."
)


async def _get_client() -> TrademarksClient:
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is None:
            _client = TrademarksClient(_settings)
            atexit.register(_close_client_atexit)
    assert _client is not None
    return _client


def _close_client_atexit() -> None:
    if _client is None:
        return
    try:
        asyncio.run(_client.aclose())
    except RuntimeError:
        pass


def _with_disclaimer(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("disclaimer", DISCLAIMER)
    return payload


def _invalid_hosted_key() -> dict[str, Any]:
    return _with_disclaimer(
        invalid_credentials(
            message_ru=(
                "Ключ нашего размещения (MCP_TRADEMARKS_API_KEY) источник не принял. "
                "Это не ответ «знаков не найдено»."
            ),
            source="наше размещение atomno-mcp",
        )
    )


def _paid_not_configured() -> dict[str, Any]:
    return _with_disclaimer(
        source_not_configured(message_ru=_PAID_SEARCH_HELP, source=SOURCE_PAID)
    )


def _paid_spec_closed() -> dict[str, Any]:
    return _with_disclaimer(spec_closed(message_ru=_SPEC_CLOSED_HELP, source=SOURCE_PAID))


async def _hosted_call(name: str, coro_factory) -> dict[str, Any]:
    if not _settings.has_token:
        return _paid_not_configured()
    try:
        result = await coro_factory()
        return _with_disclaimer(result)
    except BackendError as exc:
        if exc.status_code in (401, 403):
            return _invalid_hosted_key()
        logger.warning("%s backend %s: %s", name, exc.status_code, exc.detail)
        return _with_disclaimer(
            {
                "error": "backend_error",
                "status": exc.status_code,
                "message": exc.detail,
            }
        )
    except TrademarksError as exc:
        logger.warning("%s failed: %s", name, exc)
        return _with_disclaimer(source_unavailable(message_ru=str(exc), source="наше размещение"))


async def _paid_or_hosted(name: str, coro_factory) -> dict[str, Any]:
    if _settings.has_fips_paid:
        return _paid_spec_closed()
    if _settings.has_token:
        return await _hosted_call(name, coro_factory)
    return _paid_not_configured()


async def _get_fips_open() -> FipsOpenClient:
    global _fips_open
    if _fips_open is not None:
        return _fips_open
    async with _client_lock:
        if _fips_open is None:
            _fips_open = FipsOpenClient(
                base_url=_settings.fips_open_base,
                timeout=_settings.timeout,
            )
    assert _fips_open is not None
    return _fips_open


async def _call(fn) -> dict[str, Any]:
    client = await _get_client()
    return await fn(client)


@mcp.tool
async def search_trademark(
    query: Annotated[str, Field(min_length=1, description="Словесное обозначение для поиска (напр. «Ромашка»).")],
    classes: Annotated[list[int] | None, Field(default=None, description="Классы МКТУ 1–45 для сужения поиска.")] = None,
    status_filter: Annotated[str, Field(default="all", description="registered — только зарегистрированные; pending — заявки; all — всё.", pattern="^(registered|pending|all)$")] = "all",
    limit: Annotated[int, Field(default=20, ge=1, le=100, description="Максимум результатов.")] = 20,
) -> dict[str, Any]:
    """Платный поиск ФИПС по названию. Без учётки — отказ с причиной. С учёткой: описание обмена закрыто, запрос не выдумываем. Не путать с «знаков не найдено»."""
    return await _paid_or_hosted(
        "search_trademark",
        lambda: _call(lambda c: c.search(query, classes, status_filter, limit)),
    )


@mcp.tool
async def assess_similarity(
    candidate: Annotated[str, Field(min_length=1, description="Обозначение-кандидат для оценки чистоты.")],
    against: Annotated[list[str] | None, Field(default=None, description="Конкретные обозначения/номера для сравнения (иначе — по реестру).")] = None,
    classes: Annotated[list[int] | None, Field(default=None, description="Классы МКТУ 1–45.")] = None,
) -> dict[str, Any]:
    """Оценка сходства без платного поиска по реестру недоступна. Честный отказ, не пустой список."""
    return await _paid_or_hosted(
        "assess_similarity",
        lambda: _call(lambda c: c.assess(candidate, against, classes)),
    )


@mcp.tool
async def get_trademark_status(
    number: Annotated[str, Field(min_length=1, description="Номер свидетельства в открытом реестре ФИПС (цифры, напр. «123456»).")],
) -> dict[str, Any]:
    """Карточка по номеру свидетельства из открытого реестра ФИПС. Ключ не нужен. Не найден — found:false; сбой источника — не «знака нет»."""
    try:
        client = await _get_fips_open()
        result = await client.get_certificate(number)
        return _with_disclaimer(result)
    except FipsOpenError as exc:
        return _with_disclaimer(
            {
                "error": "invalid_number",
                "ready": False,
                "message_ru": str(exc),
                "source": SOURCE_OPEN,
            }
        )
    except SourceUnavailable as exc:
        return _with_disclaimer(source_unavailable(message_ru=str(exc), source=SOURCE_OPEN))
    except TrademarksError as exc:
        logger.warning("get_trademark_status failed: %s", exc)
        return _with_disclaimer(source_unavailable(message_ru=str(exc), source=SOURCE_OPEN))


@mcp.tool
async def search_tmview(
    query: Annotated[str, Field(min_length=1, description="Словесное обозначение для международного поиска.")],
    classes: Annotated[list[int] | None, Field(default=None, description="Классы МКТУ 1–45.")] = None,
    territories: Annotated[list[str] | None, Field(default=None, description="Коды территорий/ведомств (напр. EM — EUIPO).")] = None,
) -> dict[str, Any]:
    """Поиск в TMview не подключён. Ответ — отказ с причиной, не пустой список."""
    if _settings.has_token:
        return await _hosted_call(
            "search_tmview",
            lambda: _call(lambda c: c.tmview(query, classes, territories)),
        )
    return _with_disclaimer(
        source_not_configured(
            message_ru=(
                "Международный поиск TMview в этом продукте не подключён. "
                "Это не ответ «знаков не найдено»."
            ),
            source=SOURCE_TMVIEW,
        )
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atomno-mcp-trademarks",
        description=(
            "MCP server: FIPS open-register card by certificate number; "
            "paid name search waits for an official machine API spec."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  atomno-mcp-trademarks\n"
            "  atomno-mcp-trademarks --transport http --port 8000\n"
            "\n"
            "Environment:\n"
            "  MCP_TRADEMARKS_FIPS_LOGIN/PASSWORD — paid FIPS search (spec closed).\n"
            "  MCP_TRADEMARKS_API_KEY   — optional hosted placement key.\n"
            "  MCP_TRADEMARKS_LOG_LEVEL — logging level (overridden by --log-level).\n"
        ),
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"atomno-mcp-trademarks {__version__}",
        help="Show version and exit.",
    )
    parser.add_argument(
        "--transport",
        "-t",
        choices=_SUPPORTED_TRANSPORTS,
        default=_DEFAULT_TRANSPORT,
        help=f"MCP transport (default: {_DEFAULT_TRANSPORT}).",
    )
    parser.add_argument(
        "--host",
        default=_DEFAULT_HTTP_HOST,
        help=f"Host for http transports (default: {_DEFAULT_HTTP_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_HTTP_PORT,
        help=f"Port for http transports (default: {_DEFAULT_HTTP_PORT}).",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        choices=_VALID_LOG_LEVELS,
        default=None,
        help="Logging level; overrides MCP_TRADEMARKS_LOG_LEVEL (default: INFO).",
    )
    return parser


def _resolve_log_level(cli_value: str | None) -> str:
    if cli_value is not None:
        return cli_value
    env_raw = os.environ.get("MCP_TRADEMARKS_LOG_LEVEL")
    if env_raw is None:
        return "INFO"
    env_norm = env_raw.strip().upper()
    if env_norm in _VALID_LOG_LEVELS:
        return env_norm
    raise ValueError(
        f"MCP_TRADEMARKS_LOG_LEVEL={env_raw!r} is invalid. "
        f"Allowed: {', '.join(_VALID_LOG_LEVELS)}."
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        log_level = _resolve_log_level(args.log_level)
    except ValueError as exc:
        parser.error(str(exc))
        return 2  # pragma: no cover

    logging.basicConfig(level=log_level)
    run_kwargs: dict[str, Any] = {"transport": args.transport}
    if args.transport in ("http", "sse", "streamable-http"):
        run_kwargs["host"] = args.host
        run_kwargs["port"] = args.port
    mcp.run(**run_kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
