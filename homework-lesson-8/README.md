# Мультиагентна дослідницька система

> Homework Lesson 8 — розширення Research Agent з hw5 до мультиагентної системи
> з Supervisor, який координує Planner, Researcher та Critic за патерном
> Plan → Research → Critique.

**Версія:** 1.3.0

## Що покращено в 1.3.0

- прибрано global thread state — Supervisor більше не покладається на `_active_thread_id`
- `thread_id` читається з `ToolRuntime.config`, тому бюджети ревізій привʼязані до реального LangGraph thread
- metadata filtering у `knowledge_search` перенесено **до rerank**, щоб не втрачати релевантні документи
- prompts стали dynamic: дата/час оновлюються на кожен новий запуск агентів
- XML parser коректно обробляє **negative integers** і **float** значення
- HITL review тепер підтримує два сценарії:
  - **edit** — пряме редагування `filename` / `content`
  - **revise** — повернення feedback Supervisor'у для переписування звіту
- direct dependencies зафіксовані exact pins у `requirements.txt`
- додано integration tests для Supervisor, HITL та knowledge-search wiring

## Архітектура

```text
User (REPL)
  │
  ▼
Supervisor Agent (create_agent + HITL middleware + InMemorySaver)
  │
  ├── 1. plan(request)       → Planner Agent      → ResearchPlan (Pydantic)
  │                            tools: web_search, knowledge_search
  │
  ├── 2. research(plan)      → Research Agent     → findings (text)
  │                            tools: web_search, read_url, knowledge_search
  │                            revision budget keyed by LangGraph thread_id
  │
  ├── 3. critique(findings)  → Critic Agent       → CritiqueResult (Pydantic)
  │       │                    tools: web_search, read_url, knowledge_search
  │       ├── verdict: APPROVE  → крок 4
  │       └── verdict: REVISE   → назад до кроку 2 (макс. 2 раунди)
  │
  └── 4. save_report(...)    → HITL gate → approve / edit / revise / reject
```

### Ключовий патерн

**Evaluator-Optimizer** (з Лекції 7): Supervisor оркеструє ітеративний цикл —
Critic може відхилити дослідження і повернути його Researcher'у з конкретним
зворотним зв'язком. Це забезпечує якість фінального звіту.

### Три шари абстракції

| Шар | Компоненти | Відповідальність |
|-----|-----------|-----------------|
| **Top: Supervisor** | Координатор | Роутинг, координація, ревізійний цикл, HITL |
| **Mid: Sub-Agents** | Planner, Researcher, Critic | NL → tool calls → structured output |
| **Bottom: Tools** | web_search, read_url, knowledge_search, save_report | Точний API з типізацією |

## Компоненти

### Planner Agent (`agents/planner.py`)

Декомпозує запит користувача у структурований план:
- робить попередній пошук для розуміння домену
- повертає `ResearchPlan` (goal, search_queries, sources_to_check, output_format)
- використовує `response_format` параметр `create_agent`
- створюється динамічно, тому prompt не «старіє» у long-running сесії

### Research Agent (`agents/research.py`)

Виконує дослідження за планом:
- шукає в knowledge base та інтернеті
- читає повні статті через `read_url`
- повертає текстові findings з цитатами джерел
- лічильник ревізій тепер прив'язаний до `thread_id` із runtime config, а не до global state

### Critic Agent (`agents/critic.py`)

Оцінює якість дослідження через **незалежну верифікацію**:
- самостійно шукає для перевірки фактів та актуальності
- оцінює три виміри: **Freshness**, **Completeness**, **Structure**
- повертає `CritiqueResult` з verdict (`APPROVE` / `REVISE`) та конкретним feedback
- отримує актуальну дату щоразу через dynamic prompt builder

### Supervisor Agent (`supervisor.py`)

Координатор з 4 tool-обгортками:
- `plan` → Planner Agent
- `research` → Research Agent
- `critique` → Critic Agent
- `save_report` → file I/O (HITL gated)

### HITL Flow (`main.py`)

При виклику `save_report` Supervisor зупиняється і показує превʼю звіту:
- **approve** — зберегти звіт як є
- **edit** — напряму відредагувати `filename` та/або `content` перед викликом tool
- **revise** — відправити feedback назад Supervisor'у, щоб він переписав звіт
- **reject** — скасувати збереження

## Knowledge Search і filtering

`knowledge_search` тепер працює так:
1. FAISS semantic retrieval
2. BM25 lexical retrieval
3. Reciprocal Rank Fusion (RRF)
4. **metadata filtering before rerank**
5. Infinity rerank

Це прибирає стару проблему, коли документ міг бути релевантним для `source_filter` / `page_filter`, але випадати ще до етапу фільтрації через занадто малий rerank cutoff.

## Структурований вивід (Pydantic)

### ResearchPlan

```python
class ResearchPlan(BaseModel):
    goal: str
    search_queries: list[str]
    sources_to_check: list[Literal["knowledge_base", "web"]]
    output_format: str
```

### CritiqueResult

```python
class CritiqueResult(BaseModel):
    verdict: Literal["APPROVE", "REVISE"]
    is_fresh: bool
    is_complete: bool
    is_well_structured: bool
    strengths: list[str]
    gaps: list[str]
    revision_requests: list[str]
```

## Встановлення та запуск

### Передумови

- Python 3.10+
- SGLang з Qwen3.5-35B-A3B (або OpenAI-compatible endpoint)
- TEI з Qwen3-Embedding-8B (для embeddings)
- Infinity з BAAI/bge-reranker-v2-m3 (для reranking)

### Встановлення

```bash
cd homework-lesson-8
python3 -m pip install -r requirements.txt
cp .env.example .env
# Відредагуйте .env — вкажіть URL ваших сервісів
```

### Побудова індексу (RAG)

```bash
python ingest.py
```

### Запуск

```bash
python main.py
```

## Приклад HITL-сесії

```text
You: Порівняй naive RAG та sentence-window retrieval. Напиши звіт.

  [Supervisor -> plan] Порівняй naive RAG та sentence-window retrieval...
  <- [plan] 450 chars

  [Supervisor -> research] Research these topics...
  <- [research] 3200 chars

  [Supervisor -> critique] Findings: ...
  <- [critique] 380 chars

  [Supervisor -> save_report] rag_comparison.md

  approve / edit / revise / reject: revise
  Your feedback (what to change): Додай секцію про trade-offs.

  Sending feedback to Supervisor for revision...
```

## Структура проєкту

```text
homework-lesson-8/
├── main.py
├── supervisor.py
├── agents/
│   ├── __init__.py
│   ├── planner.py
│   ├── research.py
│   └── critic.py
├── schemas.py
├── tools.py
├── retriever.py
├── tool_parser.py
├── ingest.py
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
├── data/
│   ├── langchain.pdf
│   ├── large-language-model.pdf
│   └── retrieval-augmented-generation.pdf
├── tests/
│   ├── test_main_integration.py
│   ├── test_revision_counter.py
│   ├── test_schemas.py
│   ├── test_supervisor_integration.py
│   ├── test_tool_parser.py
│   └── test_tools_integration.py
├── CHANGELOG.md
└── README.md
```

## Конфігурація

Всі параметри налаштовуються через `.env`:

| Параметр | За замовчуванням | Опис |
|----------|------------------|------|
| `API_BASE` | `http://localhost:8000/v1` | LLM endpoint (SGLang) |
| `MODEL_NAME` | `qwen3.5-35b-a3b` | Модель |
| `MAX_REVISION_ROUNDS` | `2` | Макс. раундів Critic → Researcher |
| `MAX_ITERATIONS` | `50` | Recursion limit для Supervisor |
| `MAX_SEARCH_CONTENT_LENGTH` | `4000` | Ліміт `web_search` |
| `MAX_URL_CONTENT_LENGTH` | `8000` | Ліміт `read_url` |
| `MAX_KNOWLEDGE_CONTENT_LENGTH` | `6000` | Ліміт `knowledge_search` |
| `FILTERED_RERANK_TOP_N` | `10` | Rerank cutoff для запитів із metadata filters |

Повний список — у `.env.example`.

## Тестування

Поточний набір містить **41 тест**.

### Повний запуск

```bash
python -m pytest tests/ -v
```

### Швидкий запуск integration checks без повного suite

```bash
python -m unittest \
  tests.test_main_integration \
  tests.test_supervisor_integration \
  tests.test_tools_integration
```

Покрито:
- schema validation
- XML tool parser
- revision counter logic
- HITL edit / revise wiring
- knowledge_search filter wiring
- supervisor revision budgeting by `thread_id`

## Що перевикористано з HW5

- `retriever.py` — HybridRetriever (FAISS + BM25 + RRF + Infinity reranker)
- `tool_parser.py` — Qwen3ChatWrapper для XML tool call parsing
- `ingest.py` — Pipeline: PDF → chunks → embeddings → FAISS + BM25
- tools: `web_search`, `read_url`, `knowledge_search`
- `data/` — PDF-документи

## Що нового порівняно з HW5

| Було (HW5) | Стало (HW8) |
|------------|-------------|
| Один Research Agent з 4 tools | Supervisor + 3 суб-агенти |
| Агент робить усе одразу | Plan → Research → Critique цикл |
| Одноразове дослідження | Ітеративне (макс. 2 раунди ревізії) |
| Static prompts | Dynamic prompt builders |
| Post-rerank filter | Pre-rerank metadata filtering |
