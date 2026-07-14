<!-- mcp-name: io.github.atomno-mcp/mcp-trademarks -->
# atomno-mcp-trademarks

**Проверка товарного знака прямо в AI-ассистенте** — Russian trademark clearance
for AI agents: search Rospatent/FIPS by wordmark, assess similarity, check
application status, go international via TMview. Works in Cursor, Claude Desktop,
Cline, and any MCP client.

Прежде чем вложиться в нейминг и айдентику — за секунды узнайте, свободно ли
название. Спросите ассистента «есть ли похожие знаки на „Ромашка“ в классе
кофеен?» — и получите структурированный ответ по официальным реестрам с
**справочной** оценкой риска столкновения, а не ручной перебор форм ФИПС.

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
