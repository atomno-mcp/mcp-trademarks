"""Конфигурация из переменных окружения.

Два независимых контура:

    Открытый реестр ФИПС (карточка по номеру) — без ключа.
    Платный поиск ФИПС — MCP_TRADEMARKS_FIPS_LOGIN + MCP_TRADEMARKS_FIPS_PASSWORD.
    Наше размещение — MCP_TRADEMARKS_API_KEY (отдельная услуга).

Своего договора с ФИПС у нас сейчас нет.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .fips_open import DEFAULT_FIPS_OPEN_BASE

DEFAULT_API_BASE = "https://api.atomno-mcp.ru/trademarks"
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class Settings:
    api_base: str
    token: str | None
    timeout: float
    fips_open_base: str = DEFAULT_FIPS_OPEN_BASE
    fips_login: str | None = None
    fips_password: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        base = (os.environ.get("MCP_TRADEMARKS_API_BASE") or DEFAULT_API_BASE).rstrip("/")
        token = os.environ.get("MCP_TRADEMARKS_API_KEY") or None
        try:
            timeout = float(os.environ.get("MCP_TRADEMARKS_TIMEOUT") or DEFAULT_TIMEOUT)
        except ValueError:
            timeout = DEFAULT_TIMEOUT
        open_base = (
            os.environ.get("MCP_TRADEMARKS_FIPS_OPEN_BASE") or DEFAULT_FIPS_OPEN_BASE
        ).rstrip("/")
        login = (os.environ.get("MCP_TRADEMARKS_FIPS_LOGIN") or "").strip() or None
        password = os.environ.get("MCP_TRADEMARKS_FIPS_PASSWORD") or None
        if password is not None and not password.strip():
            password = None
        return cls(
            api_base=base,
            token=token,
            timeout=timeout,
            fips_open_base=open_base,
            fips_login=login,
            fips_password=password,
        )

    @property
    def has_token(self) -> bool:
        return bool(self.token)

    @property
    def has_fips_paid(self) -> bool:
        return bool(self.fips_login and self.fips_password)
