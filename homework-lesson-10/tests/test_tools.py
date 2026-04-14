"""README req #3 — Tool correctness, ≥3 cases.

Each case is a golden entry + expected_tools list; tools_called comes from
fixtures/hw8/e2e_outputs.json recorded via LangChain callback.

README-mandated cases:
  1) Planner receives a research query → must call a search tool
  2) Researcher receives a plan → must use sources_to_check tools
  3) Supervisor receives APPROVE from Critic → must call save_report

Agent attribution: each recorded tool_call carries an "agent" field populated
by record_fixtures.py via run-tree traversal. We filter tool_calls by that
field to separate Planner's web_search from Researcher's web_search — the
two agents share the same tool names but are attributed distinctly.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from conftest import load_agent_fixtures, skip_if_stub  # noqa: E402
from eval_config import PrimaryJudgeLLM  # noqa: E402

from deepeval.metrics import ToolCorrectnessMetric  # noqa: E402
from deepeval.test_case import LLMTestCase, ToolCall  # noqa: E402


# Expected tool names per README scenarios (actual agent tools, NOT supervisor
# delegation wrappers — delegate_to_* is a routing step, not a search).
SEARCH_TOOLS = {"web_search", "knowledge_search"}
RESEARCH_TOOLS = {"web_search", "read_url", "knowledge_search"}
REPORT_TOOLS = {"save_report"}


def _to_toolcalls(raw: list[dict]) -> list[ToolCall]:
    calls = []
    for tc in raw:
        name = tc.get("name", "")
        raw_input = tc.get("input", "")
        if isinstance(raw_input, dict):
            params = raw_input
        else:
            params = {"_raw": str(raw_input)[:500]}
        calls.append(ToolCall(name=name, input_parameters=params))
    return calls


def _calls_by_agent(tool_calls: list[dict], agent: str) -> list[dict]:
    """Filter tool_calls down to a single agent via the recorded ``agent`` tag."""
    return [tc for tc in tool_calls if tc.get("agent") == agent]


@pytest.fixture(scope="module")
def e2e_records() -> list[dict]:
    return load_agent_fixtures("e2e")


def _find_by_category(records: list[dict], category: str) -> dict | None:
    for r in records:
        if r.get("category") == category:
            return r
    return None


def _assert_agent_tool_correctness(
    record: dict,
    agent: str,
    allowed: set[str],
) -> None:
    """Shared gate: filter tool_calls to ``agent`` only, intersect with
    ``allowed``, require non-empty, then measure ToolCorrectness.

    Uses the ``agent`` field populated in record_fixtures.py — no more
    substring-matching the tool name."""
    if not record or record.get("_missing_fixtures"):
        skip_if_stub(record or {"_missing_fixtures": True})
        pytest.fail("No happy_path record in e2e fixtures.")

    agent_calls = _calls_by_agent(record["tool_calls"], agent)
    agent_names = {tc["name"] for tc in agent_calls}
    hit = agent_names & allowed
    assert hit, (
        f"Agent {agent!r} never called any of {sorted(allowed)}. "
        f"Actually called (by {agent!r}): {sorted(agent_names)}. "
        f"All tool calls in trace: "
        f"{sorted({tc['name'] for tc in record['tool_calls']})}"
    )

    tc = LLMTestCase(
        input=record["input"],
        actual_output=str(record.get("final_output", "")),
        tools_called=_to_toolcalls(agent_calls),
        expected_tools=[ToolCall(name=n, input_parameters={}) for n in sorted(hit)],
    )
    metric = ToolCorrectnessMetric(threshold=0.5, model=PrimaryJudgeLLM())
    metric.measure(tc)
    assert metric.score >= 0.5, (
        f"{agent} ToolCorrectness = {metric.score:.2f}; called={sorted(agent_names)}"
    )


def test_planner_uses_search_tools(e2e_records: list[dict]) -> None:
    record = _find_by_category(e2e_records, "happy_path")
    _assert_agent_tool_correctness(record, "planner", SEARCH_TOOLS)


def test_researcher_uses_research_tools(e2e_records: list[dict]) -> None:
    record = _find_by_category(e2e_records, "happy_path")
    _assert_agent_tool_correctness(record, "researcher", RESEARCH_TOOLS)


def test_supervisor_saves_report_on_approve(e2e_records: list[dict]) -> None:
    record = _find_by_category(e2e_records, "happy_path")
    if not record or record.get("_missing_fixtures"):
        skip_if_stub(record or {"_missing_fixtures": True})
        pytest.fail("No happy_path record in e2e fixtures.")

    supervisor_calls = _calls_by_agent(record["tool_calls"], "supervisor")
    supervisor_names = {tc["name"] for tc in supervisor_calls}
    assert REPORT_TOOLS & supervisor_names, (
        "Supervisor did not call save_report on happy_path. "
        "README requirement #3: 'Supervisor отримує APPROVE від Critic → має "
        "викликати save_report'. Fix the agent pipeline or record_fixtures "
        "with auto-approve HITL hook. "
        f"Supervisor-level calls: {sorted(supervisor_names)}"
    )
    tc = LLMTestCase(
        input=record["input"],
        actual_output=str(record.get("final_output", "")),
        tools_called=_to_toolcalls(supervisor_calls),
        expected_tools=[ToolCall(name="save_report", input_parameters={})],
    )
    metric = ToolCorrectnessMetric(threshold=0.5, model=PrimaryJudgeLLM())
    metric.measure(tc)
    assert metric.score >= 0.5
