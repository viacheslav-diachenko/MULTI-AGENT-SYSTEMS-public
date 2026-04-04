# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

## [1.3.0] - 2026-04-04

### Виправлено

- **[P1] Global thread state прибрано** — `research()` більше не покладається на
  `_active_thread_id`. `thread_id` зчитується з `ToolRuntime.config`, тому бюджети
  ревізій привʼязані до реального LangGraph thread, а не до module-level state.
- **[P1] Metadata filtering перенесено до rerank pipeline** — `knowledge_search()`
  тепер передає `source_filter` / `page_filter` у `HybridRetriever.search()`, де
  фільтрація застосовується **до** Infinity rerank.
- **[P2] Frozen prompts** — статичні `*_PROMPT` константи замінено на dynamic
  prompt builders. Supervisor і Critic завжди отримують актуальні дату/час.
- **[P2] Numeric parsing у XML tool parser** — `tool_parser.py` тепер коректно
  коерсить negative integers і float значення, а не тільки `isdigit()` випадки.
- **[P2] HITL UX polish** — REPL тепер підтримує окремі сценарії:
  `approve`, `edit`, `revise`, `reject`. `edit` напряму редагує args tool call,
  `revise` повертає feedback Supervisor'у для переписування звіту.
- **[P2] Dependency drift** — `requirements.txt` переведено на exact pins, щоб
  зафіксувати стек, на якому код перевірявся локально.

### Додано

- 8 тести (було 33, стало 41):
  - +2 integration tests для Supervisor revision budgeting
  - +2 integration tests для HITL interrupt handling
  - +2 integration tests для knowledge_search filter wiring
  - +2 parser tests для negative integer / float numeric coercion
- Оновлений `README.md` з описом нового review flow, dynamic prompts та тестового набору.

## [1.2.0] - 2026-04-03

### Виправлено

- **[P1] Edit flow не детермінований** — додано явну секцію "Handling
  save_report rejection" у SUPERVISOR_PROMPT з правилами: прочитати feedback,
  переробити звіт, повторно викликати save_report. Supervisor тепер не може
  трактувати reject як скасування.
- **[P2] Revision counter глобальний** — замінено process-global `_revision_count`
  на thread-scoped `_revision_counts: dict[str, int]` з `set_active_thread()`.
  Різні conversation threads мають ізольовані бюджети ревізій.
- **[P2] `sources_to_check` не закодований у JSON Schema** — тип поля змінено
  з `list[str]` на `list[Literal["knowledge_base", "web"]]`. Тепер Planner
  бачить обмеження і в JSON Schema, і у runtime-валідації.

### Додано

- 33 тести (було 30): +3 для thread isolation revision counter.

## [1.1.0] - 2026-04-03

### Виправлено

- **[P1] HITL resume format** — `Command(resume=...)` тепер відповідає
  документованому API LangChain: `{"decisions": [...]}` замість
  `{interrupt.id: {"decisions": [...]}}`. Гілка `edit` тепер коректно
  відхиляє tool call з feedback і повертає Supervisor'у для ревізії.
- **[P1] Critic не бачив оригінального запиту** — `critique()` тепер приймає
  три аргументи: `original_request`, `plan_summary`, `findings`. Це дозволяє
  Critic оцінювати completeness відносно реального запиту користувача.
- **[P1] MAX_REVISION_ROUNDS enforced кодом** — лічильник `_revision_count`
  у `supervisor.py` жорстко обмежує кількість раундів дослідження. Раніше
  це контролювалось лише промптом.
- **[P2] Захардкоджені приватні IP** — `config.py` тепер використовує
  `localhost` defaults, що відповідає `.env.example` та `README.md`.
- **[P2] Слабка валідація схем** — `sources_to_check` обмежений
  `{"knowledge_base", "web"}` через `field_validator`. `CritiqueResult`
  перевіряє консистентність verdict/is_*/revision_requests через
  `model_validator`.

### Додано

- 30 тестів (було 7): +schema validation, +tool_parser (15 з HW5),
  +revision counter. Всі 30 PASSED.

## [1.0.0] - 2026-04-03

### Додано

- **Мультиагентна архітектура** — Supervisor + Planner + Researcher + Critic
  за патерном Plan → Research → Critique (evaluator-optimizer з Лекції 7).
- **Planner Agent** зі структурованим виводом `ResearchPlan` через
  `response_format` параметр `create_agent`. Робить попередній пошук
  для розуміння домену перед декомпозицією задачі.
- **Critic Agent** зі структурованим виводом `CritiqueResult` — оцінює
  freshness, completeness та structure дослідження. Незалежно верифікує
  знахідки через ті самі джерела (web_search, read_url, knowledge_search).
- **Ітеративний цикл** — Critic може повернути дослідження на доопрацювання
  з конкретним зворотним зв'язком (максимум 2 раунди ревізії).
- **HITL на save_report** — `HumanInTheLoopMiddleware` з `InMemorySaver`
  checkpointer. Підтримує approve / edit / reject flow через `Command(resume=...)`.
- Pydantic-схеми `ResearchPlan` та `CritiqueResult` в `schemas.py`.
- Чотири system prompts у `config.py` для всіх агентів.
- Agent-as-Tool обгортки (`plan`, `research`, `critique`) в `supervisor.py`.
- Перевикористано з HW5: `retriever.py`, `tool_parser.py`, `ingest.py`,
  інструменти (`web_search`, `read_url`, `knowledge_search`).
- `write_report` перейменовано на `save_report` для чіткості в контексті HITL.
- Unit-тести для Pydantic-схем (7 тестів).
