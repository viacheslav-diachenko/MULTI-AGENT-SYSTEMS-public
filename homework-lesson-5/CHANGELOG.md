# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

## [1.1.0] - 2026-03-24

### Додано

- **Unit-тести для XML парсера** (`test_tool_parser.py`) — 15 тестів для
  `parse_xml_tool_calls`: happy path, malformed XML, edge cases, числовий парсинг,
  whitespace handling.
- **Truncation для `web_search`** — результати пошуку обрізаються до
  `max_search_content_length` (за замовчуванням 4000 символів) з підказкою
  використати `read_url` для повного контенту.
- **Truncation для `knowledge_search`** — результати RAG-пошуку обрізаються
  до `max_knowledge_content_length` (за замовчуванням 6000 символів).
- Нові параметри конфігурації: `MAX_SEARCH_CONTENT_LENGTH`,
  `MAX_KNOWLEDGE_CONTENT_LENGTH` в `config.py`.
- Секція "Тестування" в `README.md`.
- Цей `CHANGELOG.md`.

### Змінено

- `README.md` — оновлено діаграму архітектури (truncation limits для всіх tools),
  таблицю інструментів, структуру проєкту (додано тестовий файл та CHANGELOG).

### Виправлено

- **Context overflow у `web_search`** — результати пошуку не мали обмеження
  довжини (на відміну від `read_url`), що могло призвести до переповнення
  контекстного вікна LLM при кількох послідовних пошуках.
- **Context overflow у `knowledge_search`** — результати RAG-пошуку не мали
  обмеження довжини. При великих чанках або складних запитах сумарний вивід
  міг бути непропорційно великим відносно інших tool outputs.

## [1.0.0] - 2026-03-XX

### Додано

- Research Agent з RAG на базі LangGraph `create_react_agent`.
- Knowledge Ingestion Pipeline (`ingest.py`): PDF → chunks → FAISS + BM25 JSON.
- Hybrid Retriever (`retriever.py`): FAISS semantic + BM25 lexical + Infinity reranker.
- Новий tool `knowledge_search` з hybrid retrieval та cross-encoder reranking.
- Чотири інструменти: `knowledge_search`, `web_search`, `read_url`, `write_report`.
- `Qwen3ChatWrapper` для XML tool call parsing (з hw3).
- Self-hosted інфраструктура: SGLang + TEI + Infinity на K3s.
- Context engineering: truncation `read_url` до 8000 символів.
- System prompt зі стратегією "knowledge base first".
