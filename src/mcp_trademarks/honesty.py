"""Честные исходы: «не настроено» и «не найдено» не схлопываются."""

from __future__ import annotations

from typing import Any

from . import __version__

SOURCE_OPEN = "ФИПС, открытые реестры (RUTM), карточка по номеру свидетельства"
SOURCE_PAID = "ФИПС, платный поиск информационно-поисковой системы"
SOURCE_TMVIEW = "TMview (tmdn.org)"


def _base(*, error: str, message_ru: str, source: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ready": False,
        "error": error,
        "message_ru": message_ru,
        "source": source,
        "product_version": __version__,
    }
    out.update(extra)
    return out


def source_not_configured(*, message_ru: str, source: str, **extra: Any) -> dict[str, Any]:
    return _base(error="source_not_configured", message_ru=message_ru, source=source, **extra)


def spec_closed(*, message_ru: str, source: str, **extra: Any) -> dict[str, Any]:
    return _base(error="spec_closed", message_ru=message_ru, source=source, **extra)


def invalid_credentials(*, message_ru: str, source: str, **extra: Any) -> dict[str, Any]:
    return _base(error="invalid_credentials", message_ru=message_ru, source=source, **extra)


def source_unavailable(*, message_ru: str, source: str, **extra: Any) -> dict[str, Any]:
    return _base(error="source_unavailable", message_ru=message_ru, source=source, **extra)
