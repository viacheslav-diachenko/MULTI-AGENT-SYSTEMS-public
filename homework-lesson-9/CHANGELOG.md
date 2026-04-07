# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

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
