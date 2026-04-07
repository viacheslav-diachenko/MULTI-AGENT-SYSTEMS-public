"""Planner Agent builder — uses SearchMCP tools via mcp_tools_to_langchain.

The agent is rebuilt on every ACP invocation so the system prompt picks up
a fresh datetime and the MCP tool closures reuse the caller-supplied
``FastMCP`` client (scoped to the request).
"""

from langchain.agents import create_agent

from config import create_llm, get_planner_prompt
from mcp_utils import mcp_tools_to_langchain
from schemas import ResearchPlan


async def build_planner_agent(mcp_client):
    """Build a Planner agent bound to an already-connected FastMCP client.

    Only ``web_search`` and ``knowledge_search`` are exposed to the planner
    (no ``read_url``) — preliminary domain exploration does not require
    full article extraction.
    """
    mcp_tools = await mcp_client.list_tools()
    all_lc_tools = mcp_tools_to_langchain(mcp_tools, mcp_client)
    allowed = {"web_search", "knowledge_search"}
    tools = [t for t in all_lc_tools if t.name in allowed]

    return create_agent(
        create_llm(),
        tools=tools,
        system_prompt=get_planner_prompt(),
        response_format=ResearchPlan,
    )
