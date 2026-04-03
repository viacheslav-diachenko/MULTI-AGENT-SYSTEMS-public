# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

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
