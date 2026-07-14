# Changelog

Все заметные изменения фиксируются здесь. Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [SemVer](https://semver.org/lang/ru/).

## [0.1.0] — 2026-07-04

### Added

- Тонкий MCP-клиент `atomno-mcp-trademarks` (публичный клиент + hosted corporate API, тариф Pro).
- 4 тула через hosted API (тариф Pro): `search_trademark`, `assess_similarity`,
  `get_trademark_status`, `search_tmview`.
- Фильтр по классам МКТУ во всех поисковых тулах.
- Обязательный дисклеймер о справочном характере оценки сходства в каждом ответе.
- CLI argparse (`--help/--version/--transport/--host/--port/--log-level`), env `MCP_TRADEMARKS_*`.
- Метаданные для офиц. MCP Registry (`server.json` + workflow OIDC + маркер `mcp-name`), `glama.json`, `Dockerfile`.
