"""Critic Agent builder — uses all three SearchMCP tools with structured output."""

from langchain.agents import create_agent

from config import create_llm, get_critic_prompt
from mcp_utils import mcp_tools_to_langchain
from schemas import CritiqueResult


async def build_critic_agent(mcp_client):
    """Build a Critic agent bound to an already-connected FastMCP client."""
    mcp_tools = await mcp_client.list_tools()
    tools = mcp_tools_to_langchain(mcp_tools, mcp_client)
    return create_agent(
        create_llm(),
        tools=tools,
        system_prompt=get_critic_prompt(),
        response_format=CritiqueResult,
    )
