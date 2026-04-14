# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

## [1.0.3] - 2026-04-14

### Виправлено

- **[P1] Структура не відповідала README brief-у (all files from hw8)** —
  brief прямо вимагає, щоб файли hw8 фізично лежали в
  `homework-lesson-10/`. До цієї версії ми використовували
  `sys.path.insert(0, "../homework-lesson-8")` як shortcut —
  функціонально працювало, літерально структуру не виконувало. Тепер
  усі tracked-файли hw8 скопійовано в hw10 (крім `tests/`, який
  замінено hw10-тестами згідно з brief-ом); `conftest.py` робить лише
  `sys.path.insert(0, PROJECT_ROOT)`.
- **[P2] `HW_BASE` env var став dead-code** — після структурної
  відповідності escape-hatch на hw9 більше не має сенсу. Видалено з
  `conftest.py`, `scripts/record_fixtures.py`, `scripts/generate_golden.py`,
  `eval_config.py`. `BASE_DIR = PROJECT_ROOT` скрізь.
- **[P2] `_RUNTIME_PATHS` вказували на `homework-lesson-8/...`** — після
  копіювання файлів git-diff/dirty-check мав би перевіряти
  `homework-lesson-10/`. Оновлено перелік runtime-шляхів.
- **[P3] `_corpus_hash` очікував `data/index/`** — hw8 тримає FAISS
  індекс у `index/` на верхньому рівні, не в `data/index/`. Виправлено
  шлях у `conftest.py` та `record_fixtures.py`.

### Додано

- Усі tracked-файли з `homework-lesson-8/` (крім `tests/`): `agents/`,
  `config.py`, `data/`, `demo.gif`, `ingest.py`, `main.py`,
  `retriever.py`, `schemas.py`, `supervisor.py`, `tool_parser.py`,
  `tools.py`, `.env.example`, `.gitignore`.
- Локальний FAISS `index/` (gitignored — регенерується через
  `python ingest.py`).

## [1.0.2] - 2026-04-14

### Виправлено

- **[P1] Staleness guard блокував fixture-free optional suites** —
  `_staleness_guard` був session-scoped autouse, тож відсутній
  `_manifest.json` скіпав усю сесію, включно з
  `pytest tests/smoke/ -m live` та
  `pytest tests/enhancements/test_judge_bias.py -m enhancement`, яким
  записані fixtures не потрібні. Тепер guard function-scoped;
  перевіряє `request.node.fspath` і пропускає валідацію для
  `_FIXTURE_FREE_PATHS`.
- **[P2] `tests/test_tools.py` доводив «tools викликались десь»**,
  а не «правильний агент їх викликав» — Planner і Researcher мають
  overlap по `web_search`/`knowledge_search`. Переписано під per-agent
  attribution: фільтрує `tc["agent"] == "planner"` / `"researcher"` /
  `"supervisor"` замість підстрічного збігу імен. Новий helper
  `_assert_agent_tool_correctness()` факторизує шаблон.

### Додано

- **Tool-call agent attribution у `record_fixtures.py`** — `_Capture`
  callback тепер слухає `on_chain_start` і будує мапу
  `parent_of: run_id → parent_run_id`. Коли стартує
  `delegate_to_planner` / `delegate_to_researcher` /
  `delegate_to_critic`, його `run_id` тегується іменем суб-агента;
  кожен вкладений tool_call наслідує тег через walk-up.
- Session-memoized валідація manifest-а (`_MANIFEST_STATE`) — лише
  перший gated-тест платить ціну git/hash; наступні переuse-ять
  кешований вердикт.

## [1.0.1] - 2026-04-14

### Виправлено

- **[P1] Collection падав трасою при відсутніх fixtures** —
  `load_agent_fixtures()` викидав `RuntimeError` під час
  `@pytest.mark.parametrize(...)` (collection-time), до того як
  session-scoped staleness guard встигав `pytest.skip`. Тепер повертає
  stub-запис `{"_missing_fixtures": True, ...}`; новий helper
  `skip_if_stub(record)` на початку кожного parametrized тесту
  перетворює stub на чистий `pytest.skip` з recovery-командою.
- **[P1] `tests/conftest.py` викидав items з `enhancements/` і
  `smoke/` безумовно** — README-документовані команди
  `pytest tests/enhancements/ -m enhancement` і
  `pytest tests/smoke/ -m live` не працювали. Хук тепер перевіряє,
  чи користувач явно націлив ці директорії (шлях у `config.args` або
  `-m enhancement` / `-m live`), і зберігає matching items.
- **[P2] Freshness contract перевіряв 2 хеші замість 4** —
  `_manifest.json` пише `prompts_hash`, `golden_dataset_hash`,
  `model_endpoint_hash`, `corpus_hash`, але guard валідував тільки
  перші два. Додано `_model_endpoint_hash()` (детектує зміни
  `api_base`/`model_name`/`temperature`) та `_corpus_hash()`
  (file-by-file hash FAISS index) з точковими drift-повідомленнями.
- **[P2] Tool-correctness був поблажливим** — `SEARCH_TOOLS` /
  `RESEARCH_TOOLS` містили supervisor-делегаційні wrapper-и
  (`delegate_to_planner`, `delegate_to_researcher`); це routing, не
  пошук. Видалено з expected-наборів.
- **[P2] `test_supervisor_saves_report_on_approve` тихо скіпався** —
  при відсутності `save_report` у trace tool-call викликав
  `pytest.skip`, що ховало реальну невідповідність README #3.
  Тепер `pytest.fail` з цитатою README-вимоги.

## [1.0.0] - 2026-04-14

### Додано

- **Golden dataset** — `tests/golden_dataset.json`, 15 прикладів ×
  3 категорії (happy_path 5, edge_case 5, failure_case 5).
- **Component tests** — `tests/test_planner.py` (GEval Plan Quality +
  `ResearchPlan.model_validate_json`), `tests/test_researcher.py`
  (custom GEval Groundedness + `FaithfulnessMetric` як informational),
  `tests/test_critic.py` (GEval Critique Quality + детермінований
  контракт `verdict ↔ revision_requests`).
- **Tool correctness** — `tests/test_tools.py` × 3 кейси згідно з
  README: Planner → search tools, Researcher → research tools,
  Supervisor → save_report.
- **End-to-end** — `tests/test_e2e.py`, per-category gating:
  happy_path (AnswerRelevancy + Correctness + CitationPresence),
  edge_case (ті самі з нижчими thresholds), failure_case (RefusalQuality
  як єдиний gate, AnswerRelevancy informational, Correctness skip).
- **Custom GEval метрики** (≥1 за README, по факту 4): Groundedness,
  Critique Quality, Citation Presence, Refusal Quality.
- **LLM-as-a-Jury** у `eval_config.py` — `PrimaryJudgeLLM`
  (Qwen3.5-35B, та сама target-family vLLM) + `SecondaryJudgeLLM`
  (Qwen3-Next-80B, інший scale). Probe `_secondary_available()` при
  імпорті; якщо ендпоінт недоступний — graceful fallback на
  primary-only без зриву README-compliance. Helper `jury(MetricClass)`
  повертає `[primary]` або `[primary, secondary]`; тест агрегує через
  `min(scores)` для строгого gate.
- **Reasoning-before-score + verbosity guard** — `wrap_steps()`
  додає «Reason step by step…» спереду та «Do NOT consider response
  length.» ззаду до кожних custom GEval `evaluation_steps`.
- **Enhancements поза README (опційні, виключені з default suite)** —
  `tests/enhancements/test_retriever.py` (Ragas `LLMContextRecall`
  informational), `tests/enhancements/test_judge_bias.py`
  (Position Bias Detector з Exercise 3), `tests/smoke/test_live_smoke.py`
  (live canary з `@pytest.mark.live`).
- **Freshness manifest** — `fixtures/hw8/_manifest.json` з 4 хешами
  (`prompts_hash`, `golden_dataset_hash`, `model_endpoint_hash`,
  `corpus_hash`), `base_commit`, `base_dirty`, `hw_base`,
  `generated_at`. Staleness guard у `conftest.py` перевіряє при
  старті сесії: наявність manifest-а, hash drift, code-drift
  (`git diff --stat`), dirty-tree (`git status --porcelain`),
  30-day freshness.
- **Fail-loud запис fixtures** — `scripts/record_fixtures.py`
  відмовляється запускатися, якщо runtime-шляхи hw10 dirty (без
  `--allow-dirty`).
- Per-test `thread_id` fixture + `supervisor.reset_thread` cleanup.
- `scripts/generate_golden.py` — Ragas `TestsetGenerator` stub для
  синтетичних прикладів + manual-review reminder.
