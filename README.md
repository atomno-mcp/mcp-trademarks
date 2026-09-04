<!-- mcp-name: io.github.atomno-mcp/mcp-trademarks -->

# atomno-mcp-trademarks

Клиент для запросов по товарным знакам. Реестры ФИПС и TMview ещё не подключены: ответ сообщает, что источник подключается, и не выдаёт пустой список как «знаков не найдено».

Trademark MCP client. FIPS and TMview are not connected yet.

[![Glama](https://img.shields.io/badge/Glama-listed-7c3aed.svg)](https://glama.ai/mcp/servers/atomno-mcp/mcp-trademarks)

<a href="https://glama.ai/mcp/servers/atomno-mcp/mcp-trademarks">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/atomno-mcp/mcp-trademarks/badge" alt="mcp-trademarks MCP server" />
</a>

> Оценка сходства — **справочная** и **не замена** патентного поверенного.
> Сейчас реестры не подключены.

## Что умеет сейчас

- Принимает запрос на поиск, оценку сходства, статус заявки и TMview.
- Отвечает честно: `ready: false` и причина — источник ещё не подключён.
- Не подменяет отказ пустым списком знаков.

## Что не подключено

- Реестр товарных знаков ФИПС / Роспатент
- Международная база TMview

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

| Тул | Вход | Что отвечает сейчас |
|---|---|---|
| `search_trademark` | query, classes?, status_filter?, limit? | `ready: false` — ФИПС не подключён |
| `assess_similarity` | candidate, against?, classes? | `ready: false` — оценка без реестра недоступна |
| `get_trademark_status` | number | `ready: false` — ФИПС не подключён |
| `search_tmview` | query, classes?, territories? | `ready: false` — TMview не подключён |

Каждый ответ содержит `source`, `checked_at` и `disclaimer`.

## Дисклеймер

Реестры ФИПС и TMview ещё не подключены. Оценка сходства **не заменяет**
патентного поверенного. Не аффилировано с Роспатентом, ФИПС и EUIPO/TMview.

## Лицензия

MIT © Atomno
