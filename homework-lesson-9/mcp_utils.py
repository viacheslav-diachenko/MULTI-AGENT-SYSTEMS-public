"""Bridge between FastMCP tools and LangChain StructuredTool.

Ported from lesson-9 notebook — converts MCP tool schemas (JSON Schema) into
LangChain ``StructuredTool`` objects backed by async closures so the
``create_agent`` pipeline can invoke them just like native Python tools.

The returned tools are *async* — call them from an async context
(``await agent.ainvoke(...)``).
"""

from typing import Any, Optional

from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def _build_args_model(tool_name: str, schema: dict[str, Any]):
    """Build a Pydantic model from a JSON-Schema ``inputSchema``."""
    props: dict[str, Any] = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])

    if not props:
        return None

    fields: dict[str, tuple] = {}
    for name, prop in props.items():
        py_type = _TYPE_MAP.get(prop.get("type"), str)
        default = ... if name in required else prop.get("default")
        annotation = py_type if name in required else Optional[py_type]
        fields[name] = (
            annotation,
            Field(default=default, description=prop.get("description", "")),
        )

    return create_model(f"{tool_name}_args", **fields)


def mcp_tools_to_langchain(mcp_tools, mcp_client) -> list[StructuredTool]:
    """Convert MCP tool definitions to LangChain StructuredTool objects.

    Each returned tool is async and captures ``mcp_client`` in its closure,
    so it will call that specific MCP server when invoked.
    """
    lc_tools: list[StructuredTool] = []
    for tool in mcp_tools:
        schema = tool.inputSchema or {"type": "object", "properties": {}}
        args_model = _build_args_model(tool.name, schema)

        _name, _client = tool.name, mcp_client

        async def _invoke(_name=_name, _client=_client, **kwargs):
            return str(await _client.call_tool(_name, kwargs))

        lc_tools.append(
            StructuredTool.from_function(
                coroutine=_invoke,
                name=tool.name,
                description=tool.description or tool.name,
                args_schema=args_model,
            )
        )
    return lc_tools
