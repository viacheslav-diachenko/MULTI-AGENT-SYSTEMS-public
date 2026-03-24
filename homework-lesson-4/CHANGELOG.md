# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

## [1.1.0] - 2026-03-24

### Додано

- **Unit-тести для XML парсера** (`test_agent_parser.py`) — 15 тестів для
  `parse_xml_tool_calls`: happy path, malformed XML, edge cases, числовий парсинг,
  whitespace handling.
- **Unit-тести для `@tool` декоратора** (`test_tool_decorator.py`) — 18 тестів для
  `_resolve_json_type`, auto-schema generation, TOOL_REGISTRY/TOOL_SCHEMAS population,
  перевірка required/optional параметрів та коректність JSON Schema типів.
- **Truncation для `web_search`** — результати пошуку обрізаються до
  `max_search_content_length` (за замовчуванням 4000 символів) з підказкою
  використати `read_url` для повного контенту.
- Новий параметр конфігурації `MAX_SEARCH_CONTENT_LENGTH` в `config.py`.
- Секція "Тестування" в `README.md`.
- Цей `CHANGELOG.md`.

### Змінено

- `README.md` — оновлено діаграму архітектури (truncation для обох tools),
  структуру проєкту (додано тестові файли та CHANGELOG), таблицю інструментів.

### Виправлено

- **`Optional[int]` у `@tool` декораторі** — `Optional[int]` (тобто `Union[int, None]`)
  раніше резолвився як `"string"` замість `"integer"` в JSON Schema, бо
  `_PY_TYPE_TO_JSON.get()` не знаходив `Optional[int]` серед ключів. Додано
  `_resolve_json_type()`, яка розгортає `Optional[T]` → `T` перед lookup.
- **Context overflow у `web_search`** — результати пошуку не мали обмеження
  довжини (на відміну від `read_url`), що могло призвести до переповнення
  контекстного вікна LLM при кількох послідовних пошуках.

## [1.0.0] - 2026-03-XX

### Додано

- Custom ReAct loop на базі `openai` SDK (без LangGraph/LangChain).
- Streaming вивід токенів у реальному часі через `stream=True`.
- Власний `@tool` декоратор з автогенерацією JSON Schema з type hints та docstring.
- Dual extraction strategy: native `tool_calls` + XML fallback для Qwen3/SGLang.
- `_ToolCallAccumulator` для збору tool call deltas зі streaming response.
- Graceful iteration limit з nudge-повідомленням для фінальної відповіді.
- Покращений system prompt зі структурованими секціями prompt engineering.
- Три інструменти: `web_search`, `read_url`, `write_report`.
- Context engineering: truncation `read_url` до 8000 символів.
