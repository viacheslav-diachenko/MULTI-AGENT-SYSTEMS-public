# Мультиагентна дослідницька система на MCP + ACP

> Homework Lesson 9 — розширення мультиагентної системи з
> `homework-lesson-8` на архітектуру з протоколами комунікації:
> **MCP** для інструментів і **ACP** для самих агентів.

**Версія:** 1.1.2

## Що покращено в 1.1.1

- `.env` lookup тепер теж прив'язаний до `PROJECT_ROOT`: `Settings.model_config['env_file']` — абсолютний шлях, cwd процесу більше не впливає ні на paths, ні на endpoints
- `reset_thread()` та `fresh=True` повністю чистять стан checkpointer-а (через `delete_thread` або ручну зачистку `InMemorySaver.storage`), а не тільки викидають cached Python-екземпляр


## Що покращено в 1.1.0

- multi-turn state REPL більше не губиться: shared `InMemorySaver` +
  per-thread Supervisor cache, `new` чистить через `reset_thread`
- `save_report` fail-loud через `RuntimeError`; tool results у REPL
  показуються з preview (300 chars) + status tag
- абсолютні шляхи: `DATA_DIR/INDEX_DIR/OUTPUT_DIR` нормалізуються
  відносно `PROJECT_ROOT` через `model_validator`, cwd більше не впливає
- `mcp_tools_to_langchain` fail-fast на array/object/невідомих JSON
  Schema типах (`UnsupportedMCPSchemaError`); nullable union збирається
  у `Optional[primitive]`
- startup health checks (`health.py`): async ping SearchMCP / ReportMCP /
  ACP перед відкриттям REPL з інструкцією як підняти відсутні сервери
- +13 регресійних тестів (paths, caching, schema guard-rails, save_report
  error propagation)


## Що змінилось порівняно з hw8

| Було (hw8) | Стає (hw9) |
|---|---|
| Tools як Python-функції в одному процесі | Tools виставлені як MCP-сервери (FastMCP) |
| Суб-агенти як `@tool`-обгортки для Supervisor | Суб-агенти доступні через ACP-сервер (`acp-sdk`) |
| Все працює в одному процесі | Кожен MCP/ACP сервер — окремий HTTP endpoint |
| Прямий виклик функцій | Discovery → Delegate → Collect через протоколи |

## Архітектура

```text
User (REPL: python main.py)
  │
  ▼
Supervisor Agent (local create_agent + HITL middleware + InMemorySaver)
  │
  ├── delegate_to_planner(request)      ──► ACP ──► Planner Agent  ──► MCP ──► SearchMCP
  │                                                                              (web_search,
  │                                                                               knowledge_search)
  │
  ├── delegate_to_researcher(task)      ──► ACP ──► Research Agent ──► MCP ──► SearchMCP
  │                                                                              (web_search,
  │                                                                               read_url,
  │                                                                               knowledge_search)
  │
  ├── delegate_to_critic(orig,plan,findings) ──► ACP ──► Critic Agent ──► MCP ──► SearchMCP
  │       │
  │       ├── verdict APPROVE → save_report
  │       └── verdict REVISE  → back to researcher (max revisions from config)
  │
  └── save_report(filename, content)    ──► MCP ──► ReportMCP
                                                      (save_report — HITL gated)
```

### Три шари абстракції

| Шар | Компоненти | Відповідальність |
|-----|-----------|-----------------|
| **Top: Supervisor** | Локальний `create_agent` + HITL | Routing, revision budget, HITL |
| **Mid: ACP Agents** | Planner, Researcher, Critic (acp-sdk) | NL → MCP tool calls → structured output |
| **Bottom: MCP Servers** | SearchMCP, ReportMCP (FastMCP) | Типізований протокольний API для tools і resources |

### Ключові рішення

- **Supervisor НЕ є ACP-агентом.** Він — локальний `create_agent`,
  який використовує сінхронні tool-обгортки навколо `acp_sdk.client.Client`
  і `fastmcp.Client`. Це дозволяє залишити HITL через
  `HumanInTheLoopMiddleware` без змін проти hw8.
- **Один ACP-сервер, три агенти.** Кожен `@server.agent` хендлер
  відкриває fresh `FastMCPClient` до SearchMCP, конвертує MCP tools у
  LangChain через `mcp_tools_to_langchain`, будує `create_agent` із
  поточним system prompt і викликає `agent.ainvoke(...)`. Тому prompts
  не «старіють» і кожен запит бачить актуальний datetime.
- **Структурований вивід через ACP.** Planner і Critic використовують
  `response_format=ResearchPlan|CritiqueResult`. ACP-хендлер серіалізує
  `structured_response.model_dump()` у JSON і відправляє як `Message`,
  тому контракт між Supervisor і агентами не відрізняється від hw8.
- **Thread-scoped revision budget.** Перевірка `max_revision_rounds`
  виконується в `delegate_to_researcher` *перед* віддаленим викликом, з
  ключем по `thread_id` з `ToolRuntime.config` — бюджет не тече між
  окремими розмовами.

## MCP сервери

### SearchMCP (порт 8901)

| Tool | Опис |
|---|---|
| `web_search(query, max_results?)` | DuckDuckGo з усіканням до `MAX_SEARCH_CONTENT_LENGTH` |
| `read_url(url)` | Trafilatura extraction з усіканням до `MAX_URL_CONTENT_LENGTH` |
| `knowledge_search(query, source_filter?, page_filter?)` | Hybrid (FAISS+BM25+RRF+Infinity) з pre-rerank фільтрацією |

| Resource | Що повертає |
|---|---|
| `resource://knowledge-base-stats` | JSON: `chunk_count`, `source_files`, `last_updated`, `index_dir` |

### ReportMCP (порт 8902)

| Tool | Опис |
|---|---|
| `save_report(filename, content)` | Пише Markdown у `OUTPUT_DIR` (basename sanitize + `.md` enforcement) |

| Resource | Що повертає |
|---|---|
| `resource://output-dir` | JSON: `output_dir`, `report_count`, перелік `reports` з size/mtime |

## ACP сервер (порт 8903)

Один `acp_sdk.server.Server`, три агенти:

| Agent | Tools (MCP) | Структурований вивід |
|---|---|---|
| `planner` | `web_search`, `knowledge_search` | `ResearchPlan` (JSON) |
| `researcher` | `web_search`, `read_url`, `knowledge_search` | текст findings |
| `critic` | `web_search`, `read_url`, `knowledge_search` | `CritiqueResult` (JSON) |

## Supervisor + HITL

Supervisor бачить лише **чотири tools**:

- `delegate_to_planner`
- `delegate_to_researcher`
- `delegate_to_critic`
- `save_report` (HITL gated)

`HumanInTheLoopMiddleware(interrupt_on={"save_report": True})` зупиняє
граф перед `save_report`, `main.py` показує prev `filename`/`content` і
підтримує той самий approve / edit / revise / reject flow, що й у hw8.

## Встановлення

### Передумови

- Python 3.10+
- vLLM / SGLang з OpenAI-compatible endpoint (Qwen 3.5 35B)
- TEI з `Qwen/Qwen3-Embedding-8B` для embeddings
- Infinity з `BAAI/bge-reranker-v2-m3` для reranker

### Залежності

```bash
cd homework-lesson-9
python -m pip install -r requirements.txt
cp .env.example .env
# Відредагуйте .env: ендпоінти LLM/TEI/Infinity + порти MCP/ACP
```

За замовчуванням `.env.example` вказує `DATA_DIR` і `INDEX_DIR` на
`../homework-lesson-8/...`, тому **ingest виконувати не треба**, якщо
hw8 уже проіндексований.

### Побудова індексу (лише якщо ставите hw9 окремо)

```bash
# Встановіть локальні шляхи в .env (DATA_DIR=data, INDEX_DIR=index),
# покладіть PDF у data/ та запустіть:
python ingest.py
```

## Запуск

Кожен сервер — окремий процес. Відкрийте 4 термінали (або
використайте `pm2`/`tmux`/`supervisord`):

```bash
# 1. SearchMCP  (web_search, read_url, knowledge_search)
python mcp_servers/search_mcp.py      # :8901

# 2. ReportMCP  (save_report)
python mcp_servers/report_mcp.py      # :8902

# 3. ACP сервер (planner, researcher, critic)
python acp_server.py                  # :8903

# 4. Supervisor REPL
python main.py
```

## Приклад HITL-сесії

```text
You: Порівняй naive RAG та sentence-window retrieval. Напиши звіт.

  [Supervisor -> delegate_to_planner] Порівняй naive RAG...
  <- [delegate_to_planner] 510 chars

  [Supervisor -> delegate_to_researcher] goal=..., queries=[...]
  <- [delegate_to_researcher] 3400 chars

  [Supervisor -> delegate_to_critic] Original User Request: ...
  <- [delegate_to_critic] 420 chars

  [Supervisor -> save_report] rag_comparison.md

============================================================
  ACTION REQUIRES APPROVAL
============================================================
  Tool:     save_report
  Filename: rag_comparison.md
  Preview:
  # Naive RAG vs Sentence-Window Retrieval
  ...

  approve / edit / revise / reject: approve

  Approved! Saving report via ReportMCP...
  <- [save_report] Report saved successfully: /.../output/rag_comparison.md
```

## Структура проєкту

```text
homework-lesson-9/
├── main.py                  # Supervisor REPL (HITL interrupt/resume loop)
├── supervisor.py            # Supervisor + ACP/MCP tool wrappers (cached per thread_id)
├── health.py                # Startup health checks for MCP / ACP endpoints
├── acp_server.py            # ACP server з 3 агентами
├── mcp_servers/
│   ├── __init__.py
│   ├── search_mcp.py        # SearchMCP — web_search, read_url, knowledge_search, stats resource
│   └── report_mcp.py        # ReportMCP — save_report, output-dir resource
├── agents/
│   ├── __init__.py
│   ├── planner.py           # create_agent builder (response_format=ResearchPlan)
│   ├── research.py          # create_agent builder (text output)
│   └── critic.py            # create_agent builder (response_format=CritiqueResult)
├── mcp_utils.py             # mcp_tools_to_langchain (з lesson-9 ноутбука)
├── schemas.py               # ResearchPlan, CritiqueResult (verbatim з hw8)
├── config.py                # Settings + dynamic prompts + create_llm
├── retriever.py             # Hybrid retrieval (verbatim з hw8)
├── ingest.py                # PDF → FAISS/BM25 (verbatim з hw8)
├── requirements.txt
├── .env.example
├── CHANGELOG.md
├── README.md
└── tests/
    ├── __init__.py
    ├── test_schemas.py
    ├── test_mcp_utils.py
    ├── test_supervisor_delegation.py
    ├── test_supervisor_caching.py
    └── test_config_paths.py
```

## Тестування

```bash
python -m pytest tests/ -v
```

Покрито без живих серверів:

- schema invariants (ResearchPlan / CritiqueResult model validators);
- `mcp_tools_to_langchain` — конвертація JSON Schema → Pydantic args,
  async-closure поверх fake MCP-клієнта;
- Supervisor delegation tools — monkey-patch `_acp_run` / `_mcp_save_report`,
  перевірка revision budget з thread isolation, а також контракту
  `save_report → ReportMCP`.

## Що перевикористано з hw8

- `schemas.py`, `retriever.py`, `ingest.py` — без змін.
- HITL flow і `main.py` стiль REPL (approve / edit / revise / reject).
- Patterns: dynamic prompts, thread-scoped revision budget, shared
  `create_llm()` factory.

## Що нове порівняно з hw8

| hw8 | hw9 |
|---|---|
| Tools = Python функції в одному процесі | Tools за MCP (FastMCP) |
| Sub-agents = `@tool` локальні | Sub-agents за ACP (`acp-sdk`) |
| Supervisor викликав агентів напряму | Supervisor викликає агентів через `acp_sdk.client.Client` |
| `save_report` — локальна Python tool | `save_report` — MCP tool у ReportMCP |
| — | `resource://knowledge-base-stats`, `resource://output-dir` |
