# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

## [1.1.0] - 2026-03-24

### Додано

- **Unit-тести для XML парсера** (`test_tool_parser.py`) — 15 тестів, що покривають
  happy path, malformed XML, edge cases, числовий парсинг та whitespace handling.
- **Truncation для `web_search`** — результати пошуку тепер обрізаються до
  `max_search_content_length` (за замовчуванням 4000 символів) з інформативним
  повідомленням, що спрямовує агента використати `read_url` для деталей.
- Новий параметр конфігурації `MAX_SEARCH_CONTENT_LENGTH` в `config.py` для
  незалежного контролю ліміту пошукових результатів.
- Секція "Тестування" в `README.md`.
- Цей `CHANGELOG.md`.

### Змінено

- `README.md` — оновлено опис context engineering (тепер обидва інструменти),
  діаграму архітектури (truncation для обох tools), структуру проєкту
  (додано `test_tool_parser.py` та `CHANGELOG.md`).

### Виправлено

- **Context overflow у `web_search`** — раніше результати пошуку не мали обмеження
  довжини (на відміну від `read_url`), що могло призвести до переповнення
  контекстного вікна LLM при кількох послідовних пошуках.

## [1.0.0] - 2026-03-XX

### Додано

- Початкова реалізація Research Agent на базі LangGraph `create_react_agent`.
- Три інструменти: `web_search` (DuckDuckGo), `read_url` (trafilatura), `write_report` (file I/O).
- `Qwen3ChatWrapper` — XML tool call parser для сумісності з sglang/Qwen3.5 моделями.
- `MemorySaver` checkpointer для збереження контексту бесіди.
- Pydantic Settings для конфігурації через `.env`.
- Інтерактивний REPL з streaming виводом та emoji-індикаторами tool calls.
- Context engineering: truncation `read_url` до 8000 символів.
