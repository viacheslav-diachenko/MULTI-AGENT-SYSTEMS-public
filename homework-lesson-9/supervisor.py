"""Supervisor Agent — local orchestrator talking to agents over ACP and tools over MCP.

The Supervisor exposes four LangChain tools to the LLM:

    delegate_to_planner(request)                         → ACP  → planner
    delegate_to_researcher(task)                         → ACP  → researcher
    delegate_to_critic(original_request, plan_summary, findings) → ACP → critic
    save_report(filename, content)                        → MCP → ReportMCP (HITL gated)

Sync tool bodies wrap async protocol calls via ``asyncio.run``. The HITL
middleware interrupts only on the local ``save_report`` tool (same contract
as hw8).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable

from acp_sdk.client import Client as ACPClient
from acp_sdk.models import Message, MessagePart
from fastmcp import Client as FastMCPClient
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import ToolRuntime, tool
from langgraph.checkpoint.memory import InMemorySaver

from config import Settings, create_llm, get_supervisor_prompt

logger = logging.getLogger(__name__)
settings = Settings()

# ---------------------------------------------------------------------------
# Thread-scoped revision budgeting (carried over from hw8)
# ---------------------------------------------------------------------------

_revision_counts: dict[str, int] = {}

# Shared checkpointer + per-thread Supervisor cache so multi-turn REPL
# conversations preserve LangGraph state across turns. Previously
# build_supervisor() minted a new InMemorySaver on every user input,
# silently erasing conversation history and checkpoints.
_checkpointer = InMemorySaver()
_supervisors: dict[str, Any] = {}


def reset_revision_counter(thread_id: str) -> None:
    _revision_counts[thread_id] = 0


def _increment_revision_count(thread_id: str) -> int:
    count = _revision_counts.get(thread_id, 0) + 1
    _revision_counts[thread_id] = count
    return count


def _get_thread_id(runtime: ToolRuntime) -> str:
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    if not thread_id:
        logger.warning("Missing thread_id in tool runtime config; using fallback")
        return "default-thread"
    return str(thread_id)


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


def _arun(coro: Awaitable[Any]) -> Any:
    """Run an async coroutine from a sync LangChain tool body.

    LangGraph streams the Supervisor synchronously, so there is no outer
    loop here and ``asyncio.run`` is safe.
    """
    return asyncio.run(coro)


async def _acp_run(agent_name: str, text: str) -> str:
    async with ACPClient(
        base_url=settings.acp_base_url,
        headers={"Content-Type": "application/json"},
    ) as client:
        run = await client.run_sync(
            agent=agent_name,
            input=[Message(role="user", parts=[MessagePart(content=text)])],
        )
    if not run.output:
        return ""
    last = run.output[-1]
    parts = getattr(last, "parts", None) or []
    if not parts:
        return ""
    return parts[0].content or ""


async def _mcp_save_report(filename: str, content: str) -> str:
    async with FastMCPClient(settings.report_mcp_url) as client:
        result = await client.call_tool("save_report", {"filename": filename, "content": content})
    return str(result)


# ---------------------------------------------------------------------------
# Supervisor tools
# ---------------------------------------------------------------------------


@tool
def delegate_to_planner(request: str) -> str:
    """Ask the remote Planner (via ACP) to build a structured ResearchPlan.

    Args:
        request: The user's original research question.
    """
    return _arun(_acp_run("planner", request))


@tool
def delegate_to_researcher(task: str, runtime: ToolRuntime) -> str:
    """Ask the remote Researcher (via ACP) to execute a research plan.

    Args:
        task: The research plan details or revision instructions to execute.
    """
    thread_id = _get_thread_id(runtime)
    count = _increment_revision_count(thread_id)
    max_total_calls = settings.max_revision_rounds + 1  # initial + N revisions
    if count > max_total_calls:
        return (
            f"REVISION LIMIT REACHED ({settings.max_revision_rounds} revision rounds). "
            "You must proceed with the current findings. Call save_report now."
        )
    if count > 1:
        logger.info(
            "Research revision round %d/%d for thread %s",
            count - 1, settings.max_revision_rounds, thread_id,
        )
    return _arun(_acp_run("researcher", task))


@tool
def delegate_to_critic(original_request: str, plan_summary: str, findings: str) -> str:
    """Ask the remote Critic (via ACP) to evaluate findings.

    Args:
        original_request: The user's original research question.
        plan_summary: Brief summary of the research plan (goal + queries).
        findings: The research findings to evaluate.
    """
    prompt = (
        f"## Original User Request\n{original_request}\n\n"
        f"## Research Plan\n{plan_summary}\n\n"
        f"## Research Findings to Evaluate\n{findings}"
    )
    return _arun(_acp_run("critic", prompt))


@tool
def save_report(filename: str, content: str) -> str:
    """Save the final Markdown report via ReportMCP (HITL gated).

    Args:
        filename: Target filename (e.g. ``rag_comparison.md``).
        content: Full Markdown content of the report.
    """
    return _arun(_mcp_save_report(filename, content))


# ---------------------------------------------------------------------------
# Supervisor builder
# ---------------------------------------------------------------------------


def _build_supervisor_instance(checkpointer):
    """Build a Supervisor agent bound to a specific checkpointer."""
    return create_agent(
        create_llm(settings),
        tools=[
            delegate_to_planner,
            delegate_to_researcher,
            delegate_to_critic,
            save_report,
        ],
        system_prompt=get_supervisor_prompt(settings),
        middleware=[
            HumanInTheLoopMiddleware(interrupt_on={"save_report": True}),
        ],
        checkpointer=checkpointer,
    )


def build_supervisor():
    """Create a one-shot Supervisor with its own private InMemorySaver.

    Kept for ad-hoc tooling and tests. The REPL should use
    :func:`get_or_create_supervisor` so conversation state survives
    across turns.
    """
    return _build_supervisor_instance(InMemorySaver())


def _clear_checkpointer_state(thread_id: str) -> None:
    """Best-effort wipe of all LangGraph checkpoints for a thread.

    ``_supervisors.pop`` only drops the cached Python instance; the
    shared ``InMemorySaver`` still holds checkpoints keyed by
    ``thread_id``, so a rebuilt Supervisor would silently recover the
    old conversation state. This helper tries ``delete_thread`` first
    (the supported BaseCheckpointSaver API in recent langgraph releases)
    and falls back to poking the InMemorySaver's internal dict storage
    if that method is not available.
    """
    deleter = getattr(_checkpointer, "delete_thread", None)
    if callable(deleter):
        try:
            deleter(thread_id)
            return
        except Exception:  # pragma: no cover — defensive
            logger.warning(
                "delete_thread failed for thread %s; falling back to manual cleanup",
                thread_id,
                exc_info=True,
            )

    for attr_name in ("storage", "writes", "blobs"):
        store = getattr(_checkpointer, attr_name, None)
        if not isinstance(store, dict):
            continue
        stale_keys = [
            key for key in list(store.keys())
            if isinstance(key, tuple) and key and key[0] == thread_id
        ]
        for key in stale_keys:
            store.pop(key, None)


def get_or_create_supervisor(thread_id: str, *, fresh: bool = False):
    """Return a Supervisor bound to the shared module-level checkpointer.

    The first call for a given ``thread_id`` builds a fresh agent;
    subsequent calls return the cached instance so LangGraph checkpoints
    and conversation history persist across REPL turns. Pass
    ``fresh=True`` (or call :func:`reset_thread`) to discard both the
    cached agent *and* any checkpoints stored under ``thread_id``.
    """
    if fresh:
        reset_thread(thread_id)
    if thread_id not in _supervisors:
        _supervisors[thread_id] = _build_supervisor_instance(_checkpointer)
    return _supervisors[thread_id]


def reset_thread(thread_id: str) -> None:
    """Drop the cached Supervisor, revision counter, and saved checkpoints."""
    _supervisors.pop(thread_id, None)
    _revision_counts.pop(thread_id, None)
    _clear_checkpointer_state(thread_id)
