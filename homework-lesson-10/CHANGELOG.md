# Changelog — homework-lesson-10

## 1.0.2 — 2026-04-14 — Виправлення з follow-up рев'ю

Закриває два питання з другого раунду рев'ю. Третє (відсутність canonical
fixtures + baseline-scores) залишається у користувача — вимагає live hw8
інфраструктури.

### Staleness guard більше не блокує fixture-free optional suites

`_staleness_guard` був session-scoped autouse, тож відсутній `_manifest.json`
скіпав усю сесію — включно з `pytest tests/smoke/ -m live` та
`pytest tests/enhancements/test_judge_bias.py -m enhancement`, яким записані
fixtures не потрібні.

Виправлення в `conftest.py`:
- Guard став function-scoped autouse; перевіряє `request.node.fspath` і
  пропускає валідацію для шляхів у `_FIXTURE_FREE_PATHS`
  (`tests/smoke/`, `tests/enhancements/test_judge_bias.py`).
- Сама валідація manifest-а memoize-ється на сесію (`_MANIFEST_STATE`) —
  лише перший gated-тест платить ціну git/hash; наступні переuse-ять
  кешований вердикт.

### Tool-calls тепер тегуються агентом під час запису

`record_fixtures.py` раніше клав tool-calls у плаский список, а
per-agent розкладка робилась через підстрічний збіг імен (`"planner" in n`).
Оскільки Planner і Researcher можуть викликати ті самі `web_search` /
`knowledge_search`, тести могли довести лише «ці tools викликались десь у
trace happy_path», а не «правильний агент їх викликав».

Виправлення в `scripts/record_fixtures.py`:
- `_Capture` callback тепер слухає `on_chain_start` додатково до
  `on_tool_start` і будує мапу `parent_of: run_id → parent_run_id`.
- Коли стартує supervisor-делегаційний tool (`delegate_to_planner`,
  `delegate_to_researcher`, `delegate_to_critic`), його `run_id`
  тегується іменем суб-агента у `agent_tag_of`.
- Кожен захоплений tool_call отримує нове поле `"agent"`: walk-up по
  `parent_of` до найближчого делегаційного тегу, fallback — `"supervisor"`
  (для `save_report` і самих делегацій).
- `_write_per_agent` тепер фільтрує по `tc.get("agent") == role` замість
  підстрічного матчу — Planner-овий і Researcher-овий `web_search`
  розрізняються.

### tests/test_tools.py тепер споживає поле agent

Переписав три README-обов'язкові tool-correctness тести під per-agent
зрізи trace-у:

- `test_planner_uses_search_tools` фільтрує `tool_calls` через
  `tc["agent"] == "planner"`, перетинає з `SEARCH_TOOLS`.
- `test_researcher_uses_research_tools` — те саме з `"researcher"` проти
  `RESEARCH_TOOLS`.
- `test_supervisor_saves_report_on_approve` — фільтрує по `"supervisor"` і
  вимагає `save_report` саме на цьому scope; випадковий виклик
  save_report з вкладеного агента більше не пройде як success.

Усі три тепер `pytest.fail` з інформативними повідомленнями, що показують
і agent-scoped виклики, і повний trace — fail відразу скеровує діагноз
(чи це проблема pipeline агента, чи callback-attribution).

Спільний хелпер `_assert_agent_tool_correctness(record, agent, allowed)`
факторизує паттерн: filter → intersect → require non-empty → measure
`ToolCorrectnessMetric`.

### Лишається відкритим (потребує live hw8 інфри)

- Канонічні fixtures ще відсутні (`fixtures/hw8/` порожня). Потрібен
  живий hw8 supervisor + tool-сервери. User action:
  `python scripts/record_fixtures.py`.
- Baseline scores TBD до першого `deepeval test run tests/`.

---

## 1.0.1 — 2026-04-14 — Виправлення рев'ю (collection hardening, суворіші gates)

Застосовано виправлення з рев'ю початкового scaffold-у. Усі чотири
погоджені пункти закриті:

### Collection більше не падає при відсутніх fixtures

`conftest.load_agent_fixtures()` раніше викидав `RuntimeError`, коли
fixtures відсутні — але викликається він у `@pytest.mark.parametrize(...)`,
який оцінюється під час *collection*, до того як session-scoped staleness
guard встигає `pytest.skip`. Результат: користувач бачив трасу замість
дружнього повідомлення «запусти scripts/record_fixtures.py».

Виправлення:
- `load_agent_fixtures()` повертає stub-запис
  `{"_missing_fixtures": True, ...}` коли fixture-файлу нема.
- Новий хелпер `conftest.skip_if_stub(record)` — викликається першим
  рядком кожного parametrized тесту. Перетворює stub на чистий
  `pytest.skip` з recovery-командою.
- Session-scoped staleness guard все одно спрацьовує, коли сам manifest
  відсутній → whole-session skip з тим самим recovery.

### Freshness contract тепер покриває всі manifest-хеші

`_manifest.json` пише чотири хеші; guard перевіряв тільки два. Додано:
- `_model_endpoint_hash()` — детектує зміни `api_base` / `model_name` /
  `temperature`.
- `_corpus_hash()` — детектує зміни FAISS index (file-by-file).

Обидва тепер перевіряються в `_verify_manifest()` з точковими повідомленнями
про drift.

### Optional suites поважають документовані run-команди

`tests/conftest.py::pytest_collection_modifyitems` раніше безумовно
викидав items з `tests/enhancements/` і `tests/smoke/` — це ламало
README-документовані команди:
- `pytest tests/enhancements/ -m enhancement`
- `pytest tests/smoke/ -m live`

Виправлення: хук тепер перевіряє, чи користувач явно націлив ці
директорії (через шлях у `config.args` або `-m enhancement` / `-m live`)
і зберігає матчингові items.

### Tool correctness став суворішим

- `SEARCH_TOOLS` / `RESEARCH_TOOLS` більше не включають supervisor-
  делегаційні wrapper-и (`delegate_to_planner`, `delegate_to_researcher`).
  Делегація — це routing, не пошук. Очікувані набори — реальні tools
  агента (`web_search`, `knowledge_search`, `read_url`).
- `test_supervisor_saves_report_on_approve` раніше викликав `pytest.skip`,
  коли `save_report` був відсутній у trace tool-call — це тихо ховало
  реальну невідповідність README-вимозі. Тепер `pytest.fail` з цитатою
  README.
- Усі три tool-тести тепер `pytest.fail` (не `skip`), коли агент не
  викликав жодного tool зі свого pool — викриває agent-side регресії
  замість маскувати їх.

### Лишається відкритим

- `fixtures/hw8/` усе ще порожня. `deepeval test run tests/` у поточній
  сесії скіпається з recovery-повідомленням. Запис live fixtures
  потребує запущеного hw8 supervisor + tool-серверів, які ця сесія не
  може підняти. User action: `python scripts/record_fixtures.py`.

---

## 1.0.0 — 2026-04-14 — Початковий evaluation шар

Додано автоматизований evaluation-шар поверх існуючої мультиагентної
системи з `homework-lesson-8`.

### README-обов'язкові deliverables

- `tests/golden_dataset.json` — 15 прикладів (5 happy_path, 5 edge_case, 5 failure_case).
- `tests/test_planner.py` — Plan Quality GEval + структурна перевірка через `ResearchPlan`.
- `tests/test_researcher.py` — custom Groundedness GEval (строгий) + `FaithfulnessMetric` як informational компаньйон.
- `tests/test_critic.py` — Critique Quality GEval + детермінований verdict↔revision_requests контракт.
- `tests/test_tools.py` — ToolCorrectnessMetric × 3 кейси (Planner / Researcher / Supervisor save_report).
- `tests/test_e2e.py` — AnswerRelevancy + Correctness GEval + custom Citation Presence; per-category policy з Refusal Quality gate для failure_case.

### База

Чисте розширення `homework-lesson-8` згідно з brief-ом hw10. `conftest.py`
монтує `homework-lesson-8/` на `sys.path`, тож schemas, supervisor і
retriever імпортуються напряму. `HW_BASE` env var лишається як escape-
hatch (default `hw8`); інші значення не canonical.

### Freshness & ізоляція

- Абсолютні шляхи (`PROJECT_ROOT = Path(__file__).resolve().parent`) скрізь —
  той самий патерн, що в hw8 CHANGELOG-уроках.
- Fixtures у `fixtures/hw8/`; `_manifest.json` несе 4 хеші
  (model endpoint, prompts, corpus, golden dataset), `base_commit`,
  `base_dirty`, `hw_base`, `generated_at`.
- `conftest.py` session-scoped staleness guard: наявність manifest-а,
  hash drift, code-drift (`git diff --stat`), dirty-tree
  (`git status --porcelain`), 30-day freshness.
- `scripts/record_fixtures.py` відмовляється запускатися, якщо runtime-
  шляхи `homework-lesson-8/` dirty (без `--allow-dirty`).
- Per-test `thread_id` fixture + `supervisor.reset_thread` cleanup —
  відповідає supervisor-дисципліні hw8.

### Enhancements поза README (опційні, виключені з default suite)

- **LLM-as-a-Jury** — `eval_config.py` експонує `PrimaryJudgeLLM`
  (Qwen3.5-35B, та сама target-family) і `SecondaryJudgeLLM`
  (Qwen3-Next-80B-A3B-Instruct, інший scale/snapshot). Gating-метрики
  (Correctness, Critique Quality, Groundedness, Refusal Quality)
  агрегуються через `min(primary, secondary)`. Залишкова Qwen-family bias
  визнана; cross-vendor суддя — follow-up.
- **`tests/enhancements/test_retriever.py`** — Ragas `LLMContextRecall` як
  informational діагностика retriever-а.
- **`tests/enhancements/test_judge_bias.py`** — Position Bias Detector
  згідно з Лекцією 10 Exercise 3; пише звіт у `fixtures/_judge_bias_report.json`.
- **`tests/smoke/test_live_smoke.py`** — live canary, `@pytest.mark.live`.
- **Reasoning-before-score + verbosity guard** — `eval_config.wrap_steps()`
  додає «Reason step by step…» спереду та «Do NOT consider response length.»
  ззаду до кожного custom GEval.

### Baseline scores

Заповнюються після першого `deepeval test run tests/`. Placeholder:

```
tests/test_planner.py         — Plan Quality: TBD
tests/test_researcher.py      — Groundedness: TBD (Faithfulness: TBD)
tests/test_critic.py          — Critique Quality: TBD; verdict-contract: TBD pass-rate
tests/test_tools.py           — ToolCorrectness: TBD × 3
tests/test_e2e.py             — AnswerRelevancy / Correctness / CitationPresence / RefusalQuality: TBD
```

### Follow-up (v1.1.0)

- Розширити golden dataset до 50 прикладів згідно з рекомендацією Лекції 10.
- Додати cross-vendor суддю (OpenAI gpt-4o-mini або Claude Haiku), коли
  з'явиться ключ.
- Підключити `deepeval view` dashboard до CI.
