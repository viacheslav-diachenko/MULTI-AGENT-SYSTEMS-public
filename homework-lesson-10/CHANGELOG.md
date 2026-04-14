# Changelog — homework-lesson-10

## 1.0.2 — 2026-04-14 — Follow-up review fixes

Addresses two remaining issues from the follow-up review (the third —
missing canonical fixtures / baseline scores — still requires live hw8
infrastructure and is left as user action).

### Staleness guard no longer blocks fixture-free optional suites

`_staleness_guard` was session-scoped autouse, so a missing `_manifest.json`
skipped the entire session — including `pytest tests/smoke/ -m live` and
`pytest tests/enhancements/test_judge_bias.py -m enhancement`, which do not
need recorded fixtures.

Fix in `conftest.py`:
- Guard is now function-scoped autouse; it inspects `request.node.fspath`
  and skips validation for paths in `_FIXTURE_FREE_PATHS`
  (`tests/smoke/`, `tests/enhancements/test_judge_bias.py`).
- Manifest validation itself is memoized at session level (`_MANIFEST_STATE`)
  — only the first gated test pays the git/hash cost; later tests reuse the
  cached verdict.

### Tool calls now agent-tagged at recording time

`record_fixtures.py` used to collect tool calls into one flat list; per-agent
splits were inferred from substrings in the tool name (`"planner" in n`).
Because Planner and Researcher both can call overlapping tools like
`web_search` / `knowledge_search`, the test suite could only prove those
tools were used *somewhere* in the happy-path run, not that the right agent
used them.

Fix in `scripts/record_fixtures.py`:
- The `_Capture` callback now hooks `on_chain_start` in addition to
  `on_tool_start` and tracks `parent_of: run_id → parent_run_id`.
- When a supervisor delegation tool (`delegate_to_planner`,
  `delegate_to_researcher`, `delegate_to_critic`) starts, its `run_id` is
  tagged with the sub-agent name in `agent_tag_of`.
- Every captured tool call carries a new `"agent"` field: we walk the
  `parent_of` chain until we hit a delegation tag, else default to
  `"supervisor"` (save_report, the delegations themselves).
- `_write_per_agent` now filters by `tc.get("agent") == role` instead of
  substring matching — no more Planner/Researcher overlap.

### tests/test_tools.py now consumes the agent field

Rewrote the three README-mandated tool-correctness tests to assert per-agent
slices of the tool-call trace:

- `test_planner_uses_search_tools` filters `tool_calls` by
  `tc["agent"] == "planner"`, then checks intersection with `SEARCH_TOOLS`.
- `test_researcher_uses_research_tools` filters by `"researcher"` against
  `RESEARCH_TOOLS`.
- `test_supervisor_saves_report_on_approve` filters by `"supervisor"` and
  requires `save_report` to appear at that scope specifically — no more
  accidental pass when a nested agent happened to call save_report.

All three now fail with informative messages that show both the
agent-scoped calls and the full trace, so a failure immediately points to
whether the problem is the agent pipeline or the callback attribution.

Shared helper `_assert_agent_tool_correctness(record, agent, allowed)`
factors out the common pattern: filter → intersect → require non-empty →
measure `ToolCorrectnessMetric`.

### Known outstanding (user action)

- Canonical fixtures still absent (`fixtures/hw8/` empty). Needs live hw8
  supervisor + tool servers. User action: `python scripts/record_fixtures.py`.
- Baseline scores still TBD until the first `deepeval test run tests/`.

---

## 1.0.1 — 2026-04-14 — Review fixes (collection hardening, stricter gates)

Applied fixes surfaced by code review of the initial scaffold. All four
agreed-on issues addressed:

### Collection no longer crashes without fixtures

`conftest.load_agent_fixtures()` used to raise `RuntimeError` when fixtures
were missing — but it is called inside `@pytest.mark.parametrize(...)`, which
evaluates at *collection* time, before the session-scoped staleness guard
gets a chance to `pytest.skip`. Result: user saw an ugly traceback instead
of the friendly "run scripts/record_fixtures.py" message.

Fix:
- `load_agent_fixtures()` returns a single stub record
  `{"_missing_fixtures": True, ...}` when the fixture file is absent.
- New helper `conftest.skip_if_stub(record)` — called as the first line of
  every parametrized test. Turns the stub into a clean `pytest.skip` with
  a recovery command.
- Session-scoped staleness guard still fires when manifest itself is
  missing → whole-session skip with the same recovery message.

### Freshness contract now covers all manifest hashes

`_manifest.json` writes four hashes; the guard only verified two. Added:
- `_model_endpoint_hash()` — detects `api_base` / `model_name` /
  `temperature` changes.
- `_corpus_hash()` — detects FAISS index changes (file-by-file).

Both are now verified in `_verify_manifest()` with targeted drift messages.

### Optional suites honour documented run commands

`tests/conftest.py::pytest_collection_modifyitems` previously dropped every
item from `tests/enhancements/` and `tests/smoke/` unconditionally — which
broke the README-documented commands:
- `pytest tests/enhancements/ -m enhancement`
- `pytest tests/smoke/ -m live`

Fix: the hook now checks whether the user explicitly targeted those
directories (via path in `config.args` or `-m enhancement` / `-m live`) and
keeps matching items when so.

### Tool correctness tightened

- `SEARCH_TOOLS` / `RESEARCH_TOOLS` no longer include supervisor delegation
  wrappers (`delegate_to_planner`, `delegate_to_researcher`). Delegation is
  a routing step, not a search. Expected sets are the actual agent tools
  (`web_search`, `knowledge_search`, `read_url`).
- `test_supervisor_saves_report_on_approve` previously called `pytest.skip`
  when `save_report` was absent from the tool-call trace — that silently
  hid a real README-requirement failure. It now `pytest.fail`s with the
  README citation.
- All three tool tests now `pytest.fail` (not `skip`) when the agent never
  calls any tool from its expected pool — exposing agent-side regressions
  instead of masking them.

### Known outstanding

- `fixtures/hw8/` is still empty. Running `deepeval test run tests/` in the
  current session skips with the recovery message. Recording live fixtures
  requires running hw8 supervisor + tool servers, which this session cannot
  spin up. User action: `python scripts/record_fixtures.py`.

---

## 1.0.0 — 2026-04-14 — Initial evaluation layer

Added automated evaluation layer on top of the existing multi-agent system.

### README-mandated deliverables

- `tests/golden_dataset.json` — 15 examples (5 happy_path, 5 edge_case, 5 failure_case).
- `tests/test_planner.py` — Plan Quality GEval + structural check via `ResearchPlan`.
- `tests/test_researcher.py` — custom Groundedness GEval (strict), with `FaithfulnessMetric` as informational companion.
- `tests/test_critic.py` — Critique Quality GEval + deterministic verdict↔revision_requests contract check.
- `tests/test_tools.py` — ToolCorrectnessMetric × 3 cases (Planner / Researcher / Supervisor save_report).
- `tests/test_e2e.py` — AnswerRelevancy + Correctness GEval + custom Citation Presence; per-category policy with Refusal Quality gate for failure_case.

### Base

Pure extension of `homework-lesson-8` per the hw10 brief. `conftest.py`
mounts `homework-lesson-8/` on `sys.path` so schemas, supervisor and
retriever import directly. `HW_BASE` env var kept as an escape hatch
(default `hw8`); using any other value is not canonical.

### Freshness & isolation discipline

- Absolute-path anchoring (`PROJECT_ROOT = Path(__file__).resolve().parent`) throughout — same pattern as hw8 CHANGELOG lessons.
- Fixtures live at `fixtures/hw8/`; `_manifest.json` carries 4 hashes (model endpoint, prompts, corpus, golden dataset), `base_commit`, `base_dirty`, `hw_base`, `generated_at`.
- `conftest.py` session-scoped staleness guard: manifest presence, hash drift, code-drift (`git diff --stat`), dirty-tree (`git status --porcelain`), 30-day freshness.
- `scripts/record_fixtures.py` refuses to run if `homework-lesson-8/` runtime paths are dirty (unless `--allow-dirty`).
- Per-test `thread_id` fixture + `supervisor.reset_thread` cleanup — matches hw8 supervisor discipline.

### Enhancements beyond README (optional, excluded from default suite)

- **LLM-as-a-Jury** — `eval_config.py` exposes `PrimaryJudgeLLM` (Qwen3.5-35B, same target family) and `SecondaryJudgeLLM` (Qwen3-Next-80B-A3B-Instruct, different scale/snapshot). Gating metrics (Correctness, Critique Quality, Groundedness, Refusal Quality) aggregate via `min(primary, secondary)`. Residual Qwen-family bias acknowledged; cross-vendor judge is a follow-up.
- **`tests/enhancements/test_retriever.py`** — Ragas `LLMContextRecall` as informational retriever diagnostic.
- **`tests/enhancements/test_judge_bias.py`** — Position Bias Detector per Lesson 10 Exercise 3; writes report to `fixtures/_judge_bias_report.json`.
- **`tests/smoke/test_live_smoke.py`** — live canary, `@pytest.mark.live`.
- **Reasoning-before-score + verbosity guard** — `eval_config.wrap_steps()` prepends "Reason step by step…" and appends "Do NOT consider response length." to every custom GEval.

### Baseline scores

To be filled after first `deepeval test run tests/` execution. Placeholder:

```
tests/test_planner.py         — Plan Quality: TBD
tests/test_researcher.py      — Groundedness: TBD (Faithfulness: TBD)
tests/test_critic.py          — Critique Quality: TBD; verdict-contract: TBD pass-rate
tests/test_tools.py           — ToolCorrectness: TBD × 3
tests/test_e2e.py             — AnswerRelevancy / Correctness / CitationPresence / RefusalQuality: TBD
```

### Follow-up (v1.1.0)

- Extend golden dataset to 50 examples per Lesson 10 recommendation.
- Add cross-vendor judge (OpenAI gpt-4o-mini or Claude Haiku) once key is available.
- Wire `deepeval view` dashboard into CI.
