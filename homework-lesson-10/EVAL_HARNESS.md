# hw10 Evaluation Harness — нотатки реалізації

Автоматизований evaluation-шар на **DeepEval 3.9.5 + Ragas 0.4.3** поверх
мультиагентної системи з `homework-lesson-8`. Канонічне формулювання
задачі — у `README.md` (оригінальний brief hw10). Цей файл документує
харнес, що реалізує вимоги brief-у.

## База

Згідно з brief-ом hw10 — розширення `homework-lesson-8`. Усі tracked-файли
hw8 (крім `tests/`, який замінено hw10-тестами) скопійовано в
`homework-lesson-10/`. `conftest.py` додає `PROJECT_ROOT` до `sys.path`,
тож тести роблять `from schemas import ResearchPlan`,
`from supervisor import get_or_create_supervisor` тощо напряму з hw10.

## Як запускати

```bash
# 1) Один раз: записати fixtures (потрібен живий hw8 supervisor)
python scripts/record_fixtures.py

# 2) README-обов'язкове (canonical команда з brief-у)
cd homework-lesson-10 && deepeval test run tests/

# 3) Enhancements (опційно; виключені з default suite через pytest.ini)
pytest tests/enhancements/ -m enhancement

# 4) Live smoke canary
pytest tests/smoke/ -m live
```

## Mapping README-вимог → файли

| # | Вимога з brief-у | Файл |
|---|------------------|------|
| 1 | Golden dataset 15–20, 3 категорії | `tests/golden_dataset.json` (15 записів) |
| 2 | Component tests Planner / Researcher / Critic | `tests/test_planner.py`, `tests/test_researcher.py`, `tests/test_critic.py` |
| 3 | Tool correctness ≥ 3 кейси | `tests/test_tools.py` |
| 4 | End-to-end ≥ 2 метрики | `tests/test_e2e.py` |
| 5 | ≥ 1 custom GEval | Groundedness, Critique Quality, Citation Presence, Refusal Quality |
| 6 | Reasoned thresholds (не 0.95) | per-метрику в кожному тестовому файлі |
| 7 | `deepeval test run tests/` passes | canonical команда вище |

## Enhancements з Лекції 10 (опційні)

Це **не** README-вимоги; лежать поза default suite.

- **LLM-as-a-Jury** — primary (Qwen3.5-35B, та сама target-family) +
  secondary (Qwen3-Next-80B, інший scale) судді для gating-метрик.
  Secondary probe-ається при імпорті; якщо ендпоінт недоступний — suite
  graceful-fallback на primary-only без зриву README-compliance.
- **Retriever diagnostics** — `tests/enhancements/test_retriever.py`
  виконує Ragas `LLMContextRecall` на KB-expected golden-записах.
- **Position Bias Detector** — `tests/enhancements/test_judge_bias.py`
  виконує Exercise 3 з Лекції 10 і пише bias-звіт у
  `fixtures/_judge_bias_report.json`.
- **Reasoning-before-score + verbosity guard** — додається спереду /
  ззаду до кожних custom GEval `evaluation_steps` через
  `eval_config.wrap_steps()`.

Повний план і design rationale — у
`/home/administrator/.claude/plans/crystalline-sparking-pancake.md`.
