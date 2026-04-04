"""Supervisor Agent — orchestrates Plan -> Research -> Critique cycle.

Wraps three sub-agents as @tool functions and coordinates them via
an iterative evaluator-optimizer pattern. save_report is gated by
HumanInTheLoopMiddleware for user approval.
"""

import json
import logging
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import ToolRuntime, tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agents.critic import build_critic_agent
from agents.planner import build_planner_agent
from agents.research import build_research_agent
from config import Settings, get_supervisor_prompt
from tool_parser import Qwen3ChatWrapper
from tools import save_report as _save_report_tool

logger = logging.getLogger(__name__)
settings = Settings()

# Thread-scoped revision counters — keyed by thread_id so conversations
# don't interfere with each other and budgets survive checkpoint/resume.
_revision_counts: dict[str, int] = {}


def reset_revision_counter(thread_id: str) -> None:
    """Reset the revision counter for a specific thread."""
    _revision_counts[thread_id] = 0


def _get_revision_count(thread_id: str) -> int:
    """Get the current revision count for a specific thread."""
    return _revision_counts.get(thread_id, 0)


def _increment_revision_count(thread_id: str) -> int:
    """Increment and return the revision count for a specific thread."""
    count = _revision_counts.get(thread_id, 0) + 1
    _revision_counts[thread_id] = count
    return count


def _get_thread_id(runtime: ToolRuntime) -> str:
    """Extract the configured thread_id from tool runtime config."""
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    if not thread_id:
        logger.warning("Missing thread_id in tool runtime config; using fallback thread id")
        return "default-thread"
    return str(thread_id)


def _extract_message_text(result: dict[str, Any]) -> str:
    """Extract text content from the final message of an agent result."""
    messages = result.get("messages", [])
    if not messages:
        return ""

    message = messages[-1]
    text = getattr(message, "text", None)
    if isinstance(text, str) and text:
        return text

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        extracted = "\n".join(part for part in parts if part).strip()
        return extracted or str(content)
    return str(content)


# ---------------------------------------------------------------------------
# Agent-as-Tool wrappers — Supervisor sees only these 4 high-level tools
# ---------------------------------------------------------------------------

@tool
def plan(request: str) -> str:
    """Decompose a user question into a structured research plan.

    Use this FIRST for every research request. The Planner Agent will
    do preliminary searches to understand the domain, then return a
    structured plan with goal, search queries, sources, and output format.

    Args:
        request: The user's original research question.
    """
    result = build_planner_agent().invoke(
        {"messages": [{"role": "user", "content": request}]}
    )
    structured = result.get("structured_response")
    if structured is not None:
        return json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)
    return _extract_message_text(result)


@tool
def research(request: str, runtime: ToolRuntime) -> str:
    """Execute a research plan using web search, URL reading, and knowledge base.

    Use this AFTER plan() to conduct the actual research. Pass the research
    plan details (goal, queries, sources) as the request. If revising after
    critique, include the Critic's specific revision requests.

    Args:
        request: Research plan or revision instructions to execute.
    """
    thread_id = _get_thread_id(runtime)
    count = _increment_revision_count(thread_id)
    max_total_calls = settings.max_revision_rounds + 1  # initial call + N revisions

    if count > max_total_calls:
        return (
            f"REVISION LIMIT REACHED ({settings.max_revision_rounds} revision rounds). "
            "You must proceed with the current findings. Call save_report now."
        )

    if count > 1:
        logger.info(
            "Research revision round %d/%d for thread %s",
            count - 1,
            settings.max_revision_rounds,
            thread_id,
        )

    result = build_research_agent().invoke(
        {"messages": [{"role": "user", "content": request}]}
    )
    return _extract_message_text(result)


@tool
def critique(original_request: str, plan_summary: str, findings: str) -> str:
    """Evaluate research findings for freshness, completeness, and structure.

    The Critic Agent will independently verify claims using the same tools,
    then return a structured verdict (APPROVE or REVISE) with specific feedback.

    IMPORTANT: You must provide the original user request and plan summary
    so the Critic can evaluate completeness against the actual question.

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
    result = build_critic_agent().invoke(
        {"messages": [{"role": "user", "content": prompt}]}
    )
    structured = result.get("structured_response")
    if structured is not None:
        return json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)
    return _extract_message_text(result)


def build_supervisor():
    """Create a fresh Supervisor agent with a dynamic prompt and checkpointer."""
    base_llm = ChatOpenAI(
        base_url=settings.api_base,
        api_key=settings.api_key.get_secret_value(),
        model=settings.model_name,
        temperature=settings.temperature,
    )
    llm = Qwen3ChatWrapper(delegate=base_llm)

    return create_agent(
        llm,
        tools=[plan, research, critique, _save_report_tool],
        system_prompt=get_supervisor_prompt(settings),
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={"save_report": True},
            ),
        ],
        checkpointer=InMemorySaver(),
    )
