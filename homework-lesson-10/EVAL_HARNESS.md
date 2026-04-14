# hw10 Evaluation Harness — implementation notes

Automated evaluation layer built on **DeepEval 3.9.5 + Ragas 0.4.3** on top of
the multi-agent system from `homework-lesson-8`. The canonical task statement
lives in `README.md` (the original hw10 brief). This file documents the
harness that implements the brief's requirements.

## Base

Per the hw10 brief, this is a pure extension of `homework-lesson-8`. We do
not duplicate hw8 code — `conftest.py` mounts `homework-lesson-8/` on
`sys.path` so tests can `from schemas import ResearchPlan`, `from supervisor
import get_or_create_supervisor`, etc.

## How to run

```bash
# 1) One-time: record fixtures (requires running hw8 agents / MCP servers if any)
python scripts/record_fixtures.py

# 2) README-required suite
cd homework-lesson-10 && deepeval test run tests/

# 3) Enhancements (optional; excluded from default suite via pytest.ini)
pytest tests/enhancements/ -m enhancement

# 4) Live smoke canary
pytest tests/smoke/ -m live
```

## Mapping of README requirements → files

| # | README requirement | File |
|---|-------------------|------|
| 1 | Golden dataset 15–20, 3 categories | `tests/golden_dataset.json` (15 entries) |
| 2 | Component tests per Planner / Researcher / Critic | `tests/test_planner.py`, `tests/test_researcher.py`, `tests/test_critic.py` |
| 3 | Tool correctness ≥ 3 cases | `tests/test_tools.py` |
| 4 | End-to-end with ≥ 2 metrics | `tests/test_e2e.py` |
| 5 | ≥ 1 custom GEval | Groundedness, Critique Quality, Citation Presence, Refusal Quality |
| 6 | Reasoned thresholds (not 0.95 day one) | per-metric thresholds in each test file |
| 7 | `deepeval test run tests/` passes | canonical command above |

## Lesson 10 enhancements (optional)

These are *not* README requirements; they live outside the default suite.

- **LLM-as-a-Jury** — primary (Qwen3.5-35B, same target-family) + secondary
  (Qwen3-Next-80B, different scale) judges for gating metrics. Secondary is
  probed at import time; if its endpoint is unreachable, the suite falls back
  to primary-only without breaking README compliance.
- **Retriever diagnostics** — `tests/enhancements/test_retriever.py` runs
  Ragas `LLMContextRecall` on KB-expected golden entries.
- **Position Bias Detector** — `tests/enhancements/test_judge_bias.py` runs
  Lesson 10 Exercise 3 and writes a bias report to
  `fixtures/_judge_bias_report.json`.
- **Reasoning-before-score + verbosity guard** — prepended / appended to
  every custom GEval `evaluation_steps` via `eval_config.wrap_steps()`.

See `/home/administrator/.claude/plans/crystalline-sparking-pancake.md` for
the full plan and design rationale.
