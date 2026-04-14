# Автоматизоване тестування мультиагентної системи

> Homework Lesson 10 — додавання evaluation-шару поверх мультиагентної системи з
> `homework-lesson-8`. Покриваємо Planner / Researcher / Critic / Supervisor
> автоматизованими тестами через **DeepEval 3.9.5** і **Ragas 0.4.3** замість
> ручного vibe-check.

**Версія:** 1.0.2

## Що покращено в 1.0.2

- staleness-guard у `conftest.py` тепер function-scoped і пропускає
  fixture-free suites (`tests/smoke/`, `tests/enhancements/test_judge_bias.py`)
  — optional-команди з README запускаються навіть коли fixtures ще не записані
- валідація manifest-а memoize-ється на сесію — git/hash-перевірки виконуються
  один раз, а не перед кожним тестом
- `scripts/record_fixtures.py` тепер тегує кожен tool_call полем `agent` через
  обхід run-tree (`on_chain_start` + `on_tool_start`); коли стартує
  `delegate_to_planner` / `delegate_to_researcher` / `delegate_to_critic`, його
  `run_id` маркується іменем суб-агента, і всі вкладені виклики наслідують тег
- `tests/test_tools.py` переписано — фільтрує по `tc["agent"] == "planner"` /
  `"researcher"` / `"supervisor"`, а не по підстрічному збігу імен; тепер тести
  доводять «Planner викликав search tools», «Supervisor викликав save_report»,
  а не просто «ці tools з'явились десь у traці»

## Що покращено в 1.0.1

- `load_agent_fixtures()` повертає stub-запис замість `RuntimeError` при
  відсутніх fixtures — collection більше не падає трасою, тести акуратно
  скіпаються через `skip_if_stub(record)` з recovery-командою
- freshness contract тепер перевіряє всі 4 хеші з manifest-а
  (`prompts_hash`, `golden_dataset_hash`, `model_endpoint_hash`, `corpus_hash`),
  а не тільки два
- `tests/conftest.py` зберігає collection enhancements/smoke коли користувач
  явно націлив їх (`-m enhancement`, `-m live` або шлях у args) — README-команди
  для optional suites тепер реально працюють
- tool-correctness став суворішим: `delegate_to_*` прибрані з `SEARCH_TOOLS` /
  `RESEARCH_TOOLS` (це routing, не пошук); `test_supervisor_saves_report_on_approve`
  тепер `pytest.fail`, а не `pytest.skip`

## Що додано в 1.0.0

- автоматизовані тести Planner / Researcher / Critic / Supervisor
- golden dataset на 15 прикладів × 3 категорії (happy_path / edge_case / failure_case)
- `deepeval test run tests/` як CI-ready команда з усіма метриками
- LLM-as-a-Jury шар з опційним другим суддею іншого scale (Qwen3-Next-80B)
- per-category gating policy для e2e (різні метрики для happy / edge / failure)
- enhancements з Лекції 10 (retriever-метрика, position-bias detector,
  reasoning-before-score / verbosity guards) вкладені окремо й опційні

## Архітектура

```text
golden_dataset.json (15 examples × 3 categories)
  │
  ▼
scripts/record_fixtures.py  ─────►  fixtures/hw8/
  │  Live run hw8 supervisor          ├─ planner_outputs.json
  │  + LangChain callback             ├─ researcher_outputs.json
  │  + run-tree agent attribution     ├─ critic_outputs.json
  │                                   ├─ e2e_outputs.json
  │                                   └─ _manifest.json (4 hashes + commit + dirty + ts)
  │
  ▼
deepeval test run tests/
  │
  ├─ test_planner.py      → ResearchPlan parse + GEval Plan Quality
  ├─ test_researcher.py   → custom GEval Groundedness (jury) + Faithfulness (info)
  ├─ test_critic.py       → CritiqueResult contract + GEval Critique Quality (jury)
  ├─ test_tools.py        → ToolCorrectnessMetric × 3 (per-agent через tc["agent"])
  └─ test_e2e.py          → per-category gates:
                              happy_path  → AnswerRelevancy + Correctness + CitationPresence
                              edge_case   → same, нижчі thresholds
                              failure_case→ RefusalQuality (gate), AnswerRelevancy (info)

eval_config.PrimaryJudgeLLM (Qwen3.5-35B, той самий vLLM, що й target)
  + опційний SecondaryJudgeLLM (Qwen3-Next-80B, інший scale/snapshot)
  → jury-min для gating-метрик: Correctness, Critique Quality, Groundedness, RefusalQuality
```

### Ключові патерни з Лекції 10

- **Two-layer testing** (Block 1.3): для Critic — pydantic-контракт
  `verdict ↔ revision_requests` (детермінований pytest) + GEval
  Critique Quality (LLM-as-a-Judge). Дешеве + семантичне разом.
- **Per-category gating** (Block 7 — Goodhart's Law): failure_case не
  оцінюється Correctness-ом (немає sensible reference), натомість
  custom RefusalQuality перевіряє чесність відмови; AnswerRelevancy
  для refusal — informational, не gate.
- **Reasoning-before-score + verbosity guard** (Block 3.2 + 3.3): кожен
  custom GEval починається з кроку «Reason step by step…» і завершується
  «Do NOT consider response length».

## Компоненти

### Тести README-обов'язкові (`tests/`)

| Файл | README req | Метрика | Threshold |
|------|------------|---------|-----------|
| `test_planner.py` | #2 Planner | `ResearchPlan.model_validate_json` + GEval Plan Quality | 0.70 |
| `test_researcher.py` | #2 Researcher | custom GEval Groundedness (jury), Faithfulness (info) | 0.65 / info |
| `test_critic.py` | #2 Critic | `CritiqueResult` contract + GEval Critique Quality (jury) | 0.70 |
| `test_tools.py` | #3 Tool correctness × 3 | `ToolCorrectnessMetric` per `tc["agent"]` | 0.50 |
| `test_e2e.py` | #4 + #5 | AnswerRelevancy + Correctness + CitationPresence + RefusalQuality | per-category |

### Enhancements (`tests/enhancements/`, `tests/smoke/`)

Виключені з default suite через `pytest.ini norecursedirs`. Запускаються
явно: `pytest tests/enhancements/ -m enhancement`, `pytest tests/smoke/ -m live`.

| Файл | Призначення |
|------|-------------|
| `enhancements/test_retriever.py` | Ragas `LLMContextRecall` — informational діагностика retriever-а |
| `enhancements/test_judge_bias.py` | Position Bias Detector з Exercise 3 — sanity-check суддів зі swap-technique |
| `smoke/test_live_smoke.py` | live canary: 1 реальний прохід supervisor-а |

### Judge-LLMs (`eval_config.py`)

- **PrimaryJudgeLLM** — Qwen3.5-35B-A3B через `create_llm()` з hw8 (та сама
  vLLM-модель, що й target агенти). Для cheap-метрик (Plan Quality,
  Citation Presence) і як перший суддя у LLM-as-a-Jury.
- **SecondaryJudgeLLM** — Qwen3-Next-80B-A3B-Instruct (окремий ендпоінт,
  інший scale + snapshot). Probe `_secondary_available()` при імпорті:
  якщо ендпоінт недоступний — `SECONDARY_AVAILABLE = False`, і всі gating-
  метрики graceful-fallback на primary-only без зриву README-вимог.
- **`jury(MetricClass, **kwargs)`** — повертає `[primary]` або
  `[primary, secondary]`; тест агрегує через `min(scores)` для строгого gate.

## Структура даних

### Manifest (`fixtures/hw8/_manifest.json`)

```json
{
  "generated_at": "2026-04-14T...",
  "hw_base": "hw8",
  "base_commit": "<git rev-parse HEAD>",
  "base_dirty": false,
  "model_name": "qwen3.5-35b-a3b",
  "model_endpoint_hash": "sha256:...",
  "prompts_hash": "sha256:...",
  "corpus_hash": "sha256:...",
  "golden_dataset_hash": "sha256:..."
}
```

`conftest.py::_verify_manifest()` перевіряє при старті сесії всі поля з
точковими повідомленнями про drift (наприклад: «model_endpoint_hash drift —
Settings.api_base / model_name / temperature changed since recording»).

### Tagged tool_call (`fixtures/hw8/e2e_outputs.json`)

```json
{
  "name": "web_search",
  "input": {"query": "..."},
  "run_id": "...",
  "parent_run_id": "...",
  "agent": "researcher",
  "output": "..."
}
```

Поле `agent` обчислюється під час запису через обхід `parent_of`-дерева
до найближчого `delegate_to_*` тегу — Planner і Researcher тепер
розрізняються навіть коли обидва викликали `web_search`.

## Встановлення та запуск

### Передумови

- Python 3.10+
- Працююча мультиагентна система з `homework-lesson-8` (vLLM endpoint,
  embedding endpoint, FAISS index)
- (Опційно) другий vLLM-под з Qwen3-Next-80B-A3B-Instruct для secondary judge

### Встановлення

```bash
cd homework-lesson-10
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Запис fixtures (один раз)

```bash
python scripts/record_fixtures.py
```

Скрипт:
1. Перевіряє, що runtime-шляхи `homework-lesson-8/` чисті
   (`git status --porcelain` має бути порожнім; інакше `--allow-dirty`)
2. Прогоняє supervisor по 15 golden-прикладах
3. Захоплює tool_calls + per-agent outputs через LangChain callback
4. Пише `fixtures/hw8/{planner,researcher,critic,e2e}_outputs.json` + `_manifest.json`

### Запуск тестів

```bash
# README-обов'язкове (canonical command з brief-у)
deepeval test run tests/

# Optional: enhancements
pytest tests/enhancements/ -m enhancement

# Optional: live smoke canary
pytest tests/smoke/ -m live
```

## Mapping README-вимог hw10 → файли

| # | Вимога з brief-у | Файл/артефакт |
|---|------------------|---------------|
| 1 | Golden dataset 15–20, 3 категорії, JSON | `tests/golden_dataset.json` (15 записів, 5/5/5) |
| 2 | Component tests Planner / Researcher / Critic | `tests/test_planner.py`, `test_researcher.py`, `test_critic.py` |
| 3 | Tool correctness ≥ 3 кейси | `tests/test_tools.py` |
| 4 | End-to-end ≥ 2 метрики | `tests/test_e2e.py` |
| 5 | ≥ 1 custom GEval | Groundedness, Critique Quality, Citation Presence, Refusal Quality |
| 6 | Reasoned thresholds (не 0.95) | per-метрику в кожному файлі + per-category для e2e |
| 7 | `deepeval test run tests/` passes | canonical команда вище |

## Конфігурація

### Базові (з hw8 `.env`)

| Параметр | Опис |
|----------|------|
| `API_BASE` | LLM endpoint (vLLM/SGLang) — також primary judge |
| `MODEL_NAME` | Назва моделі |
| `EMBEDDING_BASE_URL` | Embedding endpoint (для retriever-а) |
| `RERANKER_URL` | Infinity reranker endpoint |

### Hw10-специфічні (env vars для secondary judge)

| Параметр | За замовчуванням | Опис |
|----------|------------------|------|
| `JUDGE_API_BASE` | `http://uaai-qwen3-next.qwen3-chat.svc:8000/v1` | endpoint Qwen3-Next-80B (опційно) |
| `JUDGE_API_KEY` | `not-needed` | API ключ secondary judge |
| `JUDGE_MODEL` | `Qwen3-Next-80B-A3B-Instruct` | назва моделі secondary judge |
| `HW_BASE` | `hw8` | escape-hatch для зміни базової домашки (canonical = hw8) |

## Структура проєкту

```text
homework-lesson-10/
├── README.md                       # цей файл
├── EVAL_HARNESS.md                 # детальна довідка по харнесу
├── CHANGELOG.md                    # історія версій
├── pytest.ini                      # canonical config (testpaths, norecursedirs, markers)
├── requirements.txt
├── conftest.py                     # sys.path mount → hw8, staleness guard, fixtures
├── eval_config.py                  # PrimaryJudgeLLM + SecondaryJudgeLLM + jury() + wrap_steps()
├── fixtures/
│   └── hw8/
│       ├── _manifest.json
│       ├── planner_outputs.json
│       ├── researcher_outputs.json
│       ├── critic_outputs.json
│       └── e2e_outputs.json
├── scripts/
│   ├── record_fixtures.py          # запис fixtures з agent-attribution
│   └── generate_golden.py          # Ragas TestsetGenerator stub
└── tests/
    ├── golden_dataset.json         # 15 прикладів × 3 категорії
    ├── conftest.py                 # collection guard (drop enhancements/smoke у default run)
    ├── test_planner.py
    ├── test_researcher.py
    ├── test_critic.py
    ├── test_tools.py
    ├── test_e2e.py
    ├── enhancements/
    │   ├── test_retriever.py       # Ragas LLMContextRecall
    │   └── test_judge_bias.py      # Position Bias Detector
    └── smoke/
        └── test_live_smoke.py      # live canary
```

## Per-category thresholds (e2e)

| Категорія | AnswerRelevancy | Correctness | CitationPresence | RefusalQuality |
|-----------|-----------------|-------------|------------------|----------------|
| `happy_path` | 0.70 (gate) | 0.60 (gate) | 0.60 (gate) | skip |
| `edge_case`  | 0.55 (gate) | 0.45 (gate) | 0.40 (gate) | skip |
| `failure_case` | informational | skip (немає sensible reference) | skip | 0.70 (gate) |

Логіка failure_case: запит «поза доменом» / «промпт-ін'єкція» — система
має чесно відмовитися; RefusalQuality перевіряє якість самої відмови
(стисло, чесно, on-topic про причину). Низька AnswerRelevancy на
refusal-відповіді — нормально (метрика погано підходить для відмов),
тому це informational, не gate.

## Тестування

```bash
# Повний запуск (canonical)
deepeval test run tests/

# Окремі файли для дебагу
deepeval test run tests/test_critic.py
deepeval test run tests/test_e2e.py

# Enhancement suites
pytest tests/enhancements/test_retriever.py -m enhancement
pytest tests/enhancements/test_judge_bias.py -m enhancement
pytest tests/smoke/test_live_smoke.py -m live
```

## Що нового порівняно з hw8

| Було (hw8) | Стало (hw10) |
|------------|--------------|
| Якість перевіряється вручну (vibe check) | Автоматизовані evals з метриками 0–1 |
| Немає golden dataset | 15 golden examples для regression testing |
| Немає CI-ready тестів | `deepeval test run tests/` запускає всі тести |
| Тестується тільки контракт коду | Тестується ще й семантика виходу через LLM-as-a-Judge |
| Один набір thresholds | Per-category gating (happy/edge/failure) |
| — | Custom метрики під специфіку: Groundedness, RefusalQuality, CitationPresence |

## Обмеження поточного релізу

- **fixtures/hw8/ ще не заповнено** — потрібен один прогін
  `python scripts/record_fixtures.py` з підключеними vLLM + embedding +
  reranker ендпоінтами hw8.
- **Baseline scores ще не зафіксовані** — після першого `deepeval test run`
  записати у `CHANGELOG.md` як baseline для подальших регресій.
- **Secondary judge (Qwen3-Next-80B) поки що уявний** — суіт працює в
  primary-only режимі без скарг; коли под буде піднятий, secondary
  активується автоматично через `_secondary_available()` probe.
