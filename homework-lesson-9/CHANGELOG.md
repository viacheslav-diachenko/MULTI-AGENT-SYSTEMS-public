# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

## [1.1.2] - 2026-04-07

### Виправлено

- **[P2] Fallback cleanup пропускав реальний `InMemorySaver.storage`** —
  `_clear_checkpointer_state` обробляв `storage` як tuple-keyed словник,
  тоді як langgraph 1.1.x документує його як `dict[str, ...]` з
  `thread_id` на верхньому рівні. Якщо `delete_thread` недоступний або
  впаде, основна історія checkpoint-ів залишалась, і rebuilt Supervisor
  міг відновити стару розмову. Тепер `storage.pop(thread_id, None)`,
  а tuple-фільтрація залишена лише для `writes`/`blobs` (які реально
  key-овані `(thread_id, ns, checkpoint_id, task_id)`).
- **[P3] Fallback-тест моделював неправильну форму storage** —
  `test_reset_thread_fallback_clears_in_memory_storage` переписано:
  `storage` тепер `{"thread-a": {...}, "thread-b": {...}}`, а
  `writes`/`blobs` — tuple-keyed. Тест валідує, що після `reset_thread`
  bucket `thread-a` зникає зі storage цілком, а всі tuple-записи з
  `thread-a` на позиції 0 — з writes/blobs; bucket `thread-b`
  залишається неторканим.

## [1.1.1] - 2026-04-07

### Виправлено

- **[P1] `.env` lookup залежав від cwd** — `Settings.model_config`
  тримав `env_file=".env"`, тому Pydantic резолвив його через cwd
  процесу. Запуск MCP/ACP сервера з іншої директорії мовчки пропускав
  реальний `.env` і падав у defaults. Тепер `env_file =
  str(PROJECT_ROOT / ".env")`, і 1.1.0 контракт «cwd більше не впливає»
  нарешті стосується і endpoint-ів / API base / портів.
- **[P2] `reset_thread()` / `fresh=True` не чистили state checkpointer-а** —
  евікція видаляла лише cached Python-екземпляр Supervisor-а, а
  shared `InMemorySaver` зберігав checkpoints по тому самому
  `thread_id`. Rebuilt Supervisor мовчки відновлював стару розмову.
  Додано `_clear_checkpointer_state(thread_id)`: спершу пробує
  документований `delete_thread` API, fallback — ручна зачистка
  InMemorySaver `storage` / `writes` / `blobs`. `get_or_create_supervisor(
  ..., fresh=True)` тепер маршрутизується через `reset_thread()`.

### Додано

- +4 тести:
  - `test_env_file_is_anchored_at_project_root` — перевіряє
    абсолютність і коректне batko шляху `env_file`.
  - `test_reset_thread_clears_checkpointer_state` — підтверджує виклик
    `delete_thread`.
  - `test_reset_thread_fallback_clears_in_memory_storage` — перевіряє
    fallback-шлях без `delete_thread`.
  - `test_fresh_flag_clears_checkpointer_state` — гарантує, що
    `fresh=True` теж чистить saver.

## [1.1.0] - 2026-04-07

### Виправлено

- **[P1] Втрачений multi-turn state** — `build_supervisor()` на кожен
  user turn створював новий `InMemorySaver`, тому LangGraph checkpoints
  і історія розмови безшумно обнулялись між запитами. Додано
  module-level `_checkpointer` та `_supervisors: dict[str, Agent]`,
  а також `get_or_create_supervisor(thread_id)` / `reset_thread()`.
  `main.py` тепер викликає `get_or_create_supervisor` на кожен турн,
  а команда `new` викликає `reset_thread` перед створенням нового
  `thread_id`. Per-turn reset revision counter збережено.
- **[P1] `save_report` глушила помилки** — ReportMCP повертав string
  `"Failed to save report: ..."` і на успіх, і на помилку, а REPL
  друкував лише довжину контенту. Тепер ReportMCP піднімає
  `RuntimeError` на `OSError`, а `process_stream_step` показує preview
  tool-відповіді (300 символів) + tool status tag, тож і успіх, і fail
  реально видно користувачу.
- **[P2] Шляхи залежали від cwd процесу** — `DATA_DIR`/`INDEX_DIR`/
  `OUTPUT_DIR` нормалізуються через `pathlib.Path` відносно нового
  `PROJECT_ROOT = Path(__file__).resolve().parent` у `model_validator`
  `Settings`. Запуск з будь-якого cwd (tmux/pm2/service) тепер
  детерміновано читає/пише у правильні директорії.
- **[P2] `mcp_tools_to_langchain` мовчки коерсив невідомі типи до
  `str`** — додано `UnsupportedMCPSchemaError` і fail-fast перевірку
  на `array`/`object`/невідомі типи. Nullable-union `[primitive, null]`
  коректно колапсує у `Optional[primitive]`.

### Додано

- `health.py` — async ping SearchMCP / ReportMCP / ACP через FastMCP та
  acp-sdk клієнти. `main.py` виконує health checks на старті REPL і
  виводить summary + команди для запуску серверів, якщо щось недоступне.
- Тести (+13):
  - `tests/test_config_paths.py` — 4 тести path normalisation,
    включно з "запуск з іншого cwd".
  - `tests/test_supervisor_caching.py` — 5 тестів на instance reuse,
    fresh rebuild, `reset_thread` eviction, shared checkpointer.
  - `tests/test_mcp_utils.py` — 3 тести fail-fast для array/object
    params та collapse union `[integer, null]` → `Optional[int]`.
  - `tests/test_supervisor_delegation.py` — 1 тест для
    `save_report → ReportMCP` error propagation.

### Змінено

- Version bump 1.0.0 → 1.1.0.

## [1.0.0] - 2026-04-07

### Додано

- **Протокольна архітектура MCP + ACP** — розширення мультиагентної
  системи з `homework-lesson-8` на патерн з окремими серверами:
  - **SearchMCP** (FastMCP, порт 8901) — виставляє `web_search`,
    `read_url`, `knowledge_search` як MCP-tools та
    `resource://knowledge-base-stats` як ресурс (counts + last-updated).
  - **ReportMCP** (FastMCP, порт 8902) — `save_report` як MCP-tool,
    `resource://output-dir` як ресурс зі списком збережених звітів.
  - **ACP Server** (acp-sdk, порт 8903) — три агенти: `planner`,
    `researcher`, `critic`. Кожен хендлер відкриває `fastmcp.Client`
    до SearchMCP, конвертує MCP-tools у LangChain формат через
    `mcp_tools_to_langchain`, будує `create_agent` з актуальним
    system-prompt і викликає `ainvoke` асинхронно.
  - **Supervisor** (локальний `create_agent`) — делегує роботу через
    `acp_sdk.client.Client` (`delegate_to_planner`,
    `delegate_to_researcher`, `delegate_to_critic`) та зберігає звіт
    через `fastmcp.Client` у ReportMCP (`save_report`).
  - **HITL на `save_report`** через `HumanInTheLoopMiddleware` — той
    самий approve / edit / revise / reject flow, що й у hw8.
- **mcp_utils.mcp_tools_to_langchain** — хелпер з лекції 9, адаптований
  у модуль з Pydantic-моделями аргументів, згенерованими з JSON Schema.
- **Dynamic prompts** — Supervisor/Critic отримують свіжий datetime на
  кожному виклику (збережено інваріант hw8 1.3.0).
- **Thread-scoped revision budgeting** — `_revision_counts` тепер
  привʼязані до `thread_id` із `ToolRuntime.config`, бюджет перевіряється
  у `delegate_to_researcher` *перед* викликом ACP, тому ліміт працює і
  для нових Researcher-виходів через мережу.
- **Structured output через ACP** — `planner` і `critic` використовують
  `response_format`, а ACP-хендлер повертає `structured_response` як
  JSON-рядок у `Message`, щоб Supervisor бачив той самий контракт, що й
  у hw8.
- **Тести (3 файли, 14 тестів):**
  - `tests/test_schemas.py` — інваріанти `ResearchPlan` / `CritiqueResult`.
  - `tests/test_mcp_utils.py` — перевірка конвертації MCP-tool → LangChain
    `StructuredTool` з async-closure (без живого MCP сервера).
  - `tests/test_supervisor_delegation.py` — delegate tools виконуються
    через monkey-patched async helpers; покриває revision budget
    (+thread isolation) і `save_report → ReportMCP`.
- **`.env.example`** — додано MCP/ACP endpoint налаштування, defaults
  `DATA_DIR`/`INDEX_DIR` показують у hw8, тому hw9 не потребує
  повторного ingest.
- **README.md** — повна архітектурна діаграма, порядок запуску серверів,
  HITL flow, мапа того, що перевикористано з hw8.

### Перевикористано з hw8 (без змін логіки)

- `schemas.py` (ResearchPlan, CritiqueResult з model validators)
- `retriever.py` (FAISS + BM25 + RRF + Infinity reranker,
  pre-rerank metadata filter)
- `ingest.py` (PyPDFLoader → RecursiveCharacterTextSplitter → FAISS/BM25)
