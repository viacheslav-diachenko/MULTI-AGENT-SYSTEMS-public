"""ACP server hosting the three remote sub-agents.

One ACPServer, three agents: ``planner``, ``researcher``, ``critic``.
Each handler opens a fresh FastMCP client to SearchMCP, builds an agent
via ``create_agent``, runs it against the caller's last message, and
returns the agent's final textual/JSON answer as a ``Message``.

Run standalone:
    python acp_server.py
"""

from __future__ import annotations

import json
import logging
from typing import Any

from acp_sdk.models import Message, MessagePart
from acp_sdk.server import Server
from fastmcp import Client as FastMCPClient

from agents.critic import build_critic_agent
from agents.planner import build_planner_agent
from agents.research import build_research_agent
from config import Settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

settings = Settings()
server = Server()


def _extract_input_text(messages: list[Message]) -> str:
    """Return the last message's first part content (plain text)."""
    if not messages:
        return ""
    last = messages[-1]
    parts = getattr(last, "parts", None) or []
    if not parts:
        return ""
    return parts[0].content or ""


def _agent_result_to_text(result: dict[str, Any]) -> str:
    """Prefer structured_response (JSON) over raw message content."""
    structured = result.get("structured_response")
    if structured is not None:
        return json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)

    msgs = result.get("messages", [])
    if not msgs:
        return ""
    msg = msgs[-1]
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content)


def _reply(text: str) -> Message:
    return Message(role="agent", parts=[MessagePart(content=text)])


# ---------------------------------------------------------------------------
# ACP agents
# ---------------------------------------------------------------------------


@server.agent(
    name="planner",
    description="Decomposes a user research request into a structured ResearchPlan (JSON).",
)
async def planner_handler(input: list[Message]) -> Message:
    user_text = _extract_input_text(input)
    async with FastMCPClient(settings.search_mcp_url) as mcp_client:
        agent = await build_planner_agent(mcp_client)
        result = await agent.ainvoke({"messages": [("user", user_text)]})
    return _reply(_agent_result_to_text(result))


@server.agent(
    name="researcher",
    description="Executes a research plan using web_search / read_url / knowledge_search.",
)
async def researcher_handler(input: list[Message]) -> Message:
    user_text = _extract_input_text(input)
    async with FastMCPClient(settings.search_mcp_url) as mcp_client:
        agent = await build_research_agent(mcp_client)
        result = await agent.ainvoke({"messages": [("user", user_text)]})
    return _reply(_agent_result_to_text(result))


@server.agent(
    name="critic",
    description="Evaluates research findings and returns a CritiqueResult (JSON).",
)
async def critic_handler(input: list[Message]) -> Message:
    user_text = _extract_input_text(input)
    async with FastMCPClient(settings.search_mcp_url) as mcp_client:
        agent = await build_critic_agent(mcp_client)
        result = await agent.ainvoke({"messages": [("user", user_text)]})
    return _reply(_agent_result_to_text(result))


def main() -> None:  # pragma: no cover — entry point
    logger.info("Starting ACP server on %s:%d", settings.acp_host, settings.acp_port)
    server.run(host=settings.acp_host, port=settings.acp_port)


if __name__ == "__main__":  # pragma: no cover
    main()
