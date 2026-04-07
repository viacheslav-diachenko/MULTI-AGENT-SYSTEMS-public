"""Unit tests for Supervisor delegation tools and revision budgeting.

The tests monkey-patch the async ACP/MCP helpers in ``supervisor`` so they
run without any live server or network access.
"""

import pytest

import supervisor


class FakeRuntime:
    """Duck-typed ToolRuntime — carries only the thread_id used by the tool."""

    def __init__(self, thread_id: str = "thread-1"):
        self.config = {"configurable": {"thread_id": thread_id}}


@pytest.fixture(autouse=True)
def _reset_counters():
    supervisor._revision_counts.clear()
    yield
    supervisor._revision_counts.clear()


@pytest.fixture
def fake_acp(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def _fake_acp_run(agent_name: str, text: str) -> str:
        calls.append((agent_name, text))
        return f"{agent_name}-response"

    monkeypatch.setattr(supervisor, "_acp_run", _fake_acp_run)
    return calls


@pytest.fixture
def fake_report_mcp(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def _fake_save(filename: str, content: str) -> str:
        calls.append((filename, content))
        return f"saved:{filename}"

    monkeypatch.setattr(supervisor, "_mcp_save_report", _fake_save)
    return calls


def test_delegate_to_planner_calls_acp(fake_acp):
    result = supervisor.delegate_to_planner.invoke({"request": "What is RAG?"})
    assert result == "planner-response"
    assert fake_acp == [("planner", "What is RAG?")]


def test_delegate_to_critic_composes_prompt(fake_acp):
    out = supervisor.delegate_to_critic.invoke({
        "original_request": "Compare RAG approaches",
        "plan_summary": "goal=..., queries=[...]",
        "findings": "Findings body",
    })
    assert out == "critic-response"
    assert fake_acp[0][0] == "critic"
    prompt = fake_acp[0][1]
    assert "Original User Request" in prompt
    assert "Research Plan" in prompt
    assert "Research Findings" in prompt


def test_delegate_to_researcher_revision_budget(fake_acp, monkeypatch):
    """After max_revision_rounds+1 calls on the same thread the tool blocks further research."""
    monkeypatch.setattr(supervisor.settings, "max_revision_rounds", 2)
    rt = FakeRuntime("thread-x")

    # 1 initial + 2 revisions = 3 allowed calls
    for _ in range(3):
        out = supervisor.delegate_to_researcher.invoke({"task": "do it"}, config={
            "configurable": {"thread_id": "thread-x"},
        })
        assert out == "researcher-response"

    # 4th call must be blocked
    blocked = supervisor.delegate_to_researcher.invoke({"task": "do it"}, config={
        "configurable": {"thread_id": "thread-x"},
    })
    assert "REVISION LIMIT REACHED" in blocked
    # ACP was not called on the blocked invocation
    assert len([c for c in fake_acp if c[0] == "researcher"]) == 3


def test_revision_counter_is_thread_scoped(fake_acp):
    supervisor.delegate_to_researcher.invoke({"task": "a"}, config={
        "configurable": {"thread_id": "t1"},
    })
    supervisor.delegate_to_researcher.invoke({"task": "b"}, config={
        "configurable": {"thread_id": "t2"},
    })
    assert supervisor._revision_counts["t1"] == 1
    assert supervisor._revision_counts["t2"] == 1


def test_save_report_tool_calls_report_mcp(fake_report_mcp):
    out = supervisor.save_report.invoke({
        "filename": "report.md",
        "content": "# hello",
    })
    assert "saved:report.md" in out
    assert fake_report_mcp == [("report.md", "# hello")]


def test_save_report_propagates_errors(monkeypatch):
    """ReportMCP failures must surface as a real exception, not a happy string."""

    async def _boom(filename: str, content: str) -> str:
        raise RuntimeError("disk full")

    monkeypatch.setattr(supervisor, "_mcp_save_report", _boom)

    with pytest.raises(RuntimeError, match="disk full"):
        supervisor.save_report.invoke({
            "filename": "report.md",
            "content": "# hello",
        })
