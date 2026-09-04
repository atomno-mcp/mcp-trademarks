"""FastMCP entrypoint для atomno-mcp-trademarks (тонкий клиент).

Тулы проксируют к hosted-бэкенду. Реестры ФИПС и TMview ещё не подключены:
ответ — ready=false, не пустой список знаков. Оценка сходства справочная,
не гарантия регистрации/отказа.
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
from .errors import BackendError, TrademarksError

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
        "Russian trademark MCP client. FIPS / Rospatent and TMview are not "
        "connected yet: every lookup returns ready=false with the source name, "
        "not an empty hit list. Do not treat that as «no trademarks found». "
        "Tools: search_trademark, assess_similarity, get_trademark_status, "
        "search_tmview. All go through the hosted API and need MCP_TRADEMARKS_API_KEY. "
        "Similarity assessment is advisory only. "
        "Key: https://atomno-mcp.ru/pricing#trademarks-pro."
    ),
)

_client: TrademarksClient | None = None
_client_lock = asyncio.Lock()
_settings = Settings.from_env()


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


def _no_token_hint() -> dict[str, Any]:
    return {
        "error": "missing_token",
        "message_ru": (
            "Не задан MCP_TRADEMARKS_API_KEY. Проверка товарных знаков — платная "
            "(тариф Pro). Ключ: https://atomno-mcp.ru/pricing#trademarks-pro"
        ),
        "disclaimer": DISCLAIMER,
    }


async def _hosted_call(name: str, coro_factory) -> dict[str, Any]:
    if not _settings.has_token:
        return _no_token_hint()
    try:
        result = await coro_factory()
        result.setdefault("disclaimer", DISCLAIMER)
        return result
    except BackendError as exc:
        if exc.status_code == 401:
            return _no_token_hint()
        logger.warning("%s backend %s: %s", name, exc.status_code, exc.detail)
        return {"error": "backend_error", "status": exc.status_code, "message": exc.detail}
    except TrademarksError as exc:
        logger.warning("%s failed: %s", name, exc)
        return {"error": "unavailable", "message": str(exc)}


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
    """Поиск по реестру ФИПС ещё не подключён. Ответ: ready=false, источник подключается. Не путать с «знаков не найдено». Тариф Pro."""
    return await _hosted_call(
        "search_trademark",
        lambda: _call(lambda c: c.search(query, classes, status_filter, limit)),
    )


@mcp.tool
async def assess_similarity(
    candidate: Annotated[str, Field(min_length=1, description="Обозначение-кандидат для оценки чистоты.")],
    against: Annotated[list[str] | None, Field(default=None, description="Конкретные обозначения/номера для сравнения (иначе — по реестру).")] = None,
    classes: Annotated[list[int] | None, Field(default=None, description="Классы МКТУ 1–45.")] = None,
) -> dict[str, Any]:
    """Оценка сходства без реестра недоступна. Ответ: ready=false, источник подключается. Тариф Pro."""
    return await _hosted_call(
        "assess_similarity",
        lambda: _call(lambda c: c.assess(candidate, against, classes)),
    )


@mcp.tool
async def get_trademark_status(
    number: Annotated[str, Field(min_length=1, description="Номер заявки или свидетельства (напр. «2024712345»).")],
) -> dict[str, Any]:
    """Статус по номеру заявки ещё не подключён (ФИПС). Ответ: ready=false, источник подключается. Тариф Pro."""
    return await _hosted_call(
        "get_trademark_status",
        lambda: _call(lambda c: c.status(number)),
    )


@mcp.tool
async def search_tmview(
    query: Annotated[str, Field(min_length=1, description="Словесное обозначение для международного поиска.")],
    classes: Annotated[list[int] | None, Field(default=None, description="Классы МКТУ 1–45.")] = None,
    territories: Annotated[list[str] | None, Field(default=None, description="Коды территорий/ведомств (напр. EM — EUIPO).")] = None,
) -> dict[str, Any]:
    """Поиск в TMview ещё не подключён. Ответ: ready=false, источник подключается. Тариф Pro."""
    return await _hosted_call(
        "search_tmview",
        lambda: _call(lambda c: c.tmview(query, classes, territories)),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atomno-mcp-trademarks",
        description=(
            "MCP server: Russian trademark client. FIPS and TMview are not "
            "connected yet; replies are honest not-ready, not empty hit lists."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  atomno-mcp-trademarks\n"
            "  atomno-mcp-trademarks --transport http --port 8000\n"
            "\n"
            "Environment:\n"
            "  MCP_TRADEMARKS_API_KEY   — Pro API key for hosted backend.\n"
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
