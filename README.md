<!-- mcp-name: io.github.atomno-mcp/mcp-trademarks -->

# atomno-mcp-trademarks

Проверка товарного знака прямо в ассистенте: поиск в Роспатенте, оценка сходства, статус заявки и международный поиск через TMview. Прежде чем вложиться в название — узнайте, свободно ли оно, без ручного перебора форм ФИПС.

Russian trademark clearance for AI agents.

[![Glama](https://img.shields.io/badge/Glama-listed-7c3aed.svg)](https://glama.ai/mcp/servers/atomno-mcp/mcp-trademarks)

<a href="https://glama.ai/mcp/servers/atomno-mcp/mcp-trademarks">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/atomno-mcp/mcp-trademarks/badge" alt="mcp-trademarks MCP server" />
</a>

> Оценка сходства носит **справочный** характер и **не является гарантией**
> регистрации или отказа. Инструмент не заменяет патентного поверенного.

## Что умеет

- **Поиск по обозначению** — тождественные и сходные знаки/заявки по слову.
- **Оценка сходства** до степени смешения (фонетика/графика/семантика), риск low/med/high.
- **Статус заявки/свидетельства** по номеру: приоритет, регистрация, классы, правообладатель, срок.
- **Международный охват** через открытую базу TMview (экспортные бренды).
- **Фильтр по классам МКТУ** (Ниццкая классификация, 45 классов) во всех поисках.

## Быстрый старт

```bash
pipx install atomno-mcp-trademarks
# или: uvx atomno-mcp-trademarks
```

Cursor / Claude Desktop (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "trademarks": {
      "command": "uvx",
      "args": ["atomno-mcp-trademarks"],
      "env": { "MCP_TRADEMARKS_API_KEY": "<ваш-ключ-Pro>" }
    }
  }
}
```

## Переменные окружения

| Переменная | Описание | Обязательна |
|---|---|---|
| `MCP_TRADEMARKS_API_KEY` | Ключ Pro (заголовок X-API-Key). [Получить](https://atomno-mcp.ru/pricing#trademarks-pro) | да |
| `MCP_TRADEMARKS_API_BASE` | URL hosted-бэкенда (по умолчанию — прод) | нет |
| `MCP_TRADEMARKS_TIMEOUT` | Таймаут HTTP, сек (default 30) | нет |
| `MCP_TRADEMARKS_LOG_LEVEL` | Уровень логирования (DEBUG/INFO/WARNING/ERROR, default WARNING) | нет |

## Тулы

| Тул | Вход | Что возвращает |
|---|---|---|
| `search_trademark` | query, classes?, status_filter?, limit? | список знаков/заявок (номер, классы, статус, правообладатель, даты) |
| `assess_similarity` | candidate, against?, classes? | ранжированный список совпадений + справочный риск по факторам |
| `get_trademark_status` | number | статус, приоритет, регистрация, классы, правообладатель, срок |
| `search_tmview` | query, classes?, territories? | международная выдача по TMview |

Каждый ответ содержит `source` (реестр-первоисточник), `retrieved_at` и `disclaimer`.

## Дисклеймер

Данные — из официальных реестров Роспатента/ФИПС и открытой базы TMview на дату
запроса. Оценка сходства/риска — **справочная**, не гарантия регистрации либо
отказа, и **не заменяет патентного поверенного**. Не аффилировано с Роспатентом,
ФИПС и EUIPO/TMview. Используется на ваш риск.

## Лицензия

MIT © Atomno
