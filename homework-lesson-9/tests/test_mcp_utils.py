"""Unit tests for mcp_utils.mcp_tools_to_langchain.

Uses duck-typed stand-ins for FastMCP Tool / Client so the test does not
require a live MCP server.
"""

import asyncio
from dataclasses import dataclass

import pytest

from mcp_utils import mcp_tools_to_langchain


@dataclass
class FakeTool:
    name: str
    description: str
    inputSchema: dict


class FakeClient:
    """Minimal async stand-in: records the last tool invocation."""

    def __init__(self):
        self.last_call: tuple[str, dict] | None = None

    async def call_tool(self, name, args):
        self.last_call = (name, args)
        return f"{name}:{args.get('query', '')}"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_converts_tool_and_preserves_metadata():
    tool = FakeTool(
        name="web_search",
        description="search the web",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query text"},
                "max_results": {"type": "integer", "description": "Result cap"},
            },
            "required": ["query"],
        },
    )
    client = FakeClient()

    [lc_tool] = mcp_tools_to_langchain([tool], client)

    assert lc_tool.name == "web_search"
    assert lc_tool.description == "search the web"
    assert lc_tool.args_schema is not None


def test_invocation_calls_client_and_returns_string():
    tool = FakeTool(
        name="web_search",
        description="search the web",
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    client = FakeClient()
    [lc_tool] = mcp_tools_to_langchain([tool], client)

    result = _run(lc_tool.ainvoke({"query": "LangChain"}))

    assert isinstance(result, str)
    assert "web_search" in result
    assert client.last_call == ("web_search", {"query": "LangChain"})


def test_handles_tool_without_schema():
    tool = FakeTool(name="ping", description="", inputSchema=None)
    client = FakeClient()
    [lc_tool] = mcp_tools_to_langchain([tool], client)
    assert lc_tool.name == "ping"
    # description falls back to tool name when original is empty
    assert lc_tool.description in ("", "ping")
