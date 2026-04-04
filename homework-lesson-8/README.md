# Мультиагентна дослідницька система

> Homework Lesson 8 — розширення Research Agent з hw5 до мультиагентної системи
> з Supervisor, який координує Planner, Researcher та Critic за патерном
> Plan → Research → Critique.

**Версія:** 1.0.0

## Архітектура

```
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
  │
  ├── 3. critique(findings)  → Critic Agent       → CritiqueResult (Pydantic)
  │       │                    tools: web_search, read_url, knowledge_search
  │       ├── verdict: APPROVE  → крок 4
  │       └── verdict: REVISE   → назад до кроку 2 (макс. 2 раунди)
  │
  └── 4. save_report(...)    → HITL gate → approve / edit / reject
```

### Ключовий патерн

**Evaluator-Optimizer** (з Лекції 7): Supervisor оркеструє ітеративний цикл —
Critic може відхилити дослідження і повернути його Researcher'у з конкретним
зворотним зв'язком. Це забезпечує якість фінального звіту.

### Три шари абстракції

| Шар | Компоненти | Відповідальність |
|-----|-----------|-----------------|
| **Top: Supervisor** | Координатор | Роутинг, координація, синтез звіту |
| **Mid: Sub-Agents** | Planner, Researcher, Critic | NL → tool calls → structured output |
| **Bottom: Tools** | web_search, read_url, knowledge_search, save_report | Точний API з типізацією |

## Компоненти

### Planner Agent (`agents/planner.py`)

Декомпозує запит користувача у структурований план:
- Робить попередній пошук для розуміння домену
- Повертає `ResearchPlan` (goal, search_queries, sources_to_check, output_format)
- Використовує `response_format` параметр `create_agent`

### Research Agent (`agents/research.py`)

Виконує дослідження за планом:
- Шукає в knowledge base та інтернеті
- Читає повні статті через `read_url`
- Повертає текстові findings з цитатами джерел

### Critic Agent (`agents/critic.py`)

Оцінює якість дослідження через **незалежну верифікацію**:
- Самостійно шукає для перевірки фактів та актуальності
- Оцінює три виміри: **Freshness**, **Completeness**, **Structure**
- Повертає `CritiqueResult` з verdict (APPROVE/REVISE) та конкретним зворотним зв'язком

### Supervisor Agent (`supervisor.py`)

Координатор з 4 tool-обгортками:
- `plan` → Planner Agent
- `research` → Research Agent
- `critique` → Critic Agent
- `save_report` → file I/O (HITL gated)

### HITL Flow (`main.py`)

При виклику `save_report` Supervisor зупиняється і показує превʼю звіту:
- **approve** — зберегти звіт як є
- **edit** — ввести feedback, Supervisor переробляє і запитує знову
- **reject** — скасувати збереження

## Структурований вивід (Pydantic)

### ResearchPlan

```python
class ResearchPlan(BaseModel):
    goal: str                     # Що досліджуємо
    search_queries: list[str]     # Конкретні пошукові запити
    sources_to_check: list[str]   # "knowledge_base", "web", або обидва
    output_format: str            # Формат фінального звіту
```

### CritiqueResult

```python
class CritiqueResult(BaseModel):
    verdict: Literal["APPROVE", "REVISE"]
    is_fresh: bool                # Дані актуальні?
    is_complete: bool             # Повне покриття запиту?
    is_well_structured: bool      # Логічна структура?
    strengths: list[str]          # Що добре
    gaps: list[str]               # Що пропущено
    revision_requests: list[str]  # Що виправити (якщо REVISE)
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
pip install -r requirements.txt
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

### Приклад сесії

```
You: Порівняй naive RAG та sentence-window retrieval. Напиши звіт.

  [Supervisor -> plan] Порівняй naive RAG та sentence-window retrieval...
  <- [plan] 450 chars

  [Supervisor -> research] Research these topics: 1) naive RAG approach...
  <- [research] 3200 chars

  [Supervisor -> critique] Findings: ...
  <- [critique] 380 chars

  [Supervisor -> research] Revision: Find 2025-2026 benchmarks...
  <- [research] 2800 chars

  [Supervisor -> critique] Updated findings: ...
  <- [critique] 290 chars

  [Supervisor -> save_report] rag_comparison.md

  ============================================================
    ACTION REQUIRES APPROVAL
  ============================================================
    Tool:     save_report
    Filename: rag_comparison.md
    Preview:
  # Порівняння RAG-підходів...
  ============================================================

    approve / edit / reject: approve

    Approved! Report saved to output/rag_comparison.md
```

## Структура проєкту

```
homework-lesson-8/
├── main.py              # REPL з HITL interrupt/resume
├── supervisor.py        # Supervisor + agent-as-tool обгортки
├── agents/
│   ├── __init__.py
│   ├── planner.py       # Planner Agent (ResearchPlan)
│   ├── research.py      # Research Agent
│   └── critic.py        # Critic Agent (CritiqueResult)
├── schemas.py           # Pydantic: ResearchPlan, CritiqueResult
├── tools.py             # web_search, read_url, knowledge_search, save_report
├── retriever.py         # Hybrid retriever (FAISS + BM25 + RRF + Infinity)
├── tool_parser.py       # Qwen3ChatWrapper (XML tool call parser)
├── ingest.py            # PDF → chunks → FAISS + BM25
├── config.py            # Settings + 4 system prompts
├── requirements.txt
├── .env.example
├── .gitignore
├── data/                # PDF-документи для RAG
│   ├── langchain.pdf
│   ├── large-language-model.pdf
│   └── retrieval-augmented-generation.pdf
├── tests/
│   └── test_schemas.py  # 7 тестів для Pydantic-схем
├── CHANGELOG.md
└── README.md
```

## Конфігурація

Всі параметри налаштовуються через `.env`:

| Параметр | За замовчуванням | Опис |
|----------|-----------------|------|
| `API_BASE` | `http://localhost:8000/v1` | LLM endpoint (SGLang) |
| `MODEL_NAME` | `qwen3.5-35b-a3b` | Модель |
| `MAX_REVISION_ROUNDS` | `2` | Макс. раундів Critic→Researcher |
| `MAX_ITERATIONS` | `50` | Recursion limit для Supervisor |
| `MAX_SEARCH_CONTENT_LENGTH` | `4000` | Ліміт web_search |
| `MAX_URL_CONTENT_LENGTH` | `8000` | Ліміт read_url |
| `MAX_KNOWLEDGE_CONTENT_LENGTH` | `6000` | Ліміт knowledge_search |

Повний список — у `.env.example`.

## Тестування

```bash
python -m pytest tests/ -v
```

## Що перевикористано з HW5

- `retriever.py` — HybridRetriever (FAISS + BM25 + RRF + Infinity reranker)
- `tool_parser.py` — Qwen3ChatWrapper для XML tool call parsing
- `ingest.py` — Pipeline: PDF → chunks → embeddings → FAISS + BM25
- Tools: `web_search`, `read_url`, `knowledge_search` (без змін)
- `data/` — PDF-документи

## Що нового порівняно з HW5

| Було (HW5) | Стало (HW8) |
|------------|------------|
| Один Research Agent з 4 tools | Supervisor + 3 суб-агенти |
| Агент робить усе одразу | Plan → Research → Critique цикл |
| Одноразове дослідження | Ітеративне (макс. 2 раунди ревізії) |
| Без підтвердження | HITL: save_report потребує approve/edit/reject |
| Лише вільний текст | Structured output (Pydantic) для Planner і Critic |
| `create_react_agent` (langgraph) | `create_agent` (langchain 1.x) |
