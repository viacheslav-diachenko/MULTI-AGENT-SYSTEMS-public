"""Research Agent builder — uses all three SearchMCP tools."""

from langchain.agents import create_agent

from config import create_llm, get_researcher_prompt
from mcp_utils import mcp_tools_to_langchain


async def build_research_agent(mcp_client):
    """Build a Research agent bound to an already-connected FastMCP client."""
    mcp_tools = await mcp_client.list_tools()
    tools = mcp_tools_to_langchain(mcp_tools, mcp_client)
    return create_agent(
        create_llm(),
        tools=tools,
        system_prompt=get_researcher_prompt(),
    )
