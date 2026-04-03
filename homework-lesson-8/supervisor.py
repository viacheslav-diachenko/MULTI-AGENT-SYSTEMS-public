"""Supervisor Agent — orchestrates Plan -> Research -> Critique cycle.

Wraps three sub-agents as @tool functions and coordinates them via
an iterative evaluator-optimizer pattern. save_report is gated by
HumanInTheLoopMiddleware for user approval.
"""

import json
import logging

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agents.critic import critic_agent
from agents.planner import planner_agent
from agents.research import research_agent
from config import SUPERVISOR_PROMPT, Settings
from tool_parser import Qwen3ChatWrapper
from tools import save_report as _save_report_tool

logger = logging.getLogger(__name__)
settings = Settings()

# Revision counter — enforced in code, not just in the prompt.
# Reset before each new user query in main.py via reset_revision_counter().
_revision_count = 0


def reset_revision_counter() -> None:
    """Reset the revision counter. Call before each new user query."""
    global _revision_count
    _revision_count = 0


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
    result = planner_agent.invoke(
        {"messages": [{"role": "user", "content": request}]}
    )
    # If structured_response is available (response_format worked), serialize it
    structured = result.get("structured_response")
    if structured is not None:
        return json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)
    # Fallback: return the last message text
    return result["messages"][-1].text


@tool
def research(request: str) -> str:
    """Execute a research plan using web search, URL reading, and knowledge base.

    Use this AFTER plan() to conduct the actual research. Pass the research
    plan details (goal, queries, sources) as the request. If revising after
    critique, include the Critic's specific revision requests.

    Args:
        request: Research plan or revision instructions to execute.
    """
    global _revision_count
    _revision_count += 1
    max_rounds = settings.max_revision_rounds + 1  # first call + N revisions

    if _revision_count > max_rounds:
        return (
            f"REVISION LIMIT REACHED ({settings.max_revision_rounds} revision rounds). "
            "You must proceed with the current findings. Call save_report now."
        )

    if _revision_count > 1:
        logger.info("Research revision round %d/%d", _revision_count - 1, settings.max_revision_rounds)

    result = research_agent.invoke(
        {"messages": [{"role": "user", "content": request}]}
    )
    return result["messages"][-1].text


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
    result = critic_agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]}
    )
    structured = result.get("structured_response")
    if structured is not None:
        return json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)
    return result["messages"][-1].text


# ---------------------------------------------------------------------------
# Supervisor Agent
# ---------------------------------------------------------------------------

_base_llm = ChatOpenAI(
    base_url=settings.api_base,
    api_key=settings.api_key.get_secret_value(),
    model=settings.model_name,
    temperature=settings.temperature,
)
_llm = Qwen3ChatWrapper(delegate=_base_llm)

supervisor = create_agent(
    _llm,
    tools=[plan, research, critique, _save_report_tool],
    system_prompt=SUPERVISOR_PROMPT,
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={"save_report": True},
        ),
    ],
    checkpointer=InMemorySaver(),
)
