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


class UnsupportedMCPSchemaError(ValueError):
    """Raised when an MCP tool input schema uses a JSON Schema feature
    this bridge does not yet translate into a Pydantic model.

    The lesson-9 helper silently coerced unknown types to ``str``, which
    produced tools whose arguments were syntactically accepted but
    semantically wrong — the kind of bug that only fires at runtime with
    confusing symptoms. This class exists so mcp_utils fails fast at
    agent-build time with a clear, actionable message instead.
    """


def _resolve_scalar_type(tool_name: str, param_name: str, json_type: Any) -> str:
    """Return a single primitive JSON Schema type or raise.

    Accepts unions like ``["integer", "null"]`` and collapses them to the
    single non-null primitive; anything richer raises the error above.
    """
    if isinstance(json_type, list):
        non_null = [t for t in json_type if t != "null"]
        if len(non_null) != 1:
            raise UnsupportedMCPSchemaError(
                f"Tool {tool_name!r} param {param_name!r} uses union type "
                f"{json_type!r}; mcp_utils only supports single primitive "
                "types or ``[primitive, 'null']``."
            )
        json_type = non_null[0]

    if json_type not in _TYPE_MAP:
        raise UnsupportedMCPSchemaError(
            f"Tool {tool_name!r} param {param_name!r} has unsupported "
            f"JSON Schema type {json_type!r}. Supported: "
            f"{sorted(_TYPE_MAP)}."
        )
    return json_type


def _build_args_model(tool_name: str, schema: dict[str, Any]):
    """Build a Pydantic model from a JSON-Schema ``inputSchema``.

    Fails loudly for schemas that use ``array`` / ``object`` / multi-type
    unions / unknown types — the bridge is intentionally kept scoped to
    primitive arguments (the only shape our SearchMCP / ReportMCP tools
    need), and silent degradation here would produce subtly broken tool
    calls at runtime.
    """
    props: dict[str, Any] = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])

    if not props:
        return None

    fields: dict[str, tuple] = {}
    for name, prop in props.items():
        if not isinstance(prop, dict):
            raise UnsupportedMCPSchemaError(
                f"Tool {tool_name!r} param {name!r} has non-dict schema "
                f"entry {prop!r}."
            )
        json_type = _resolve_scalar_type(tool_name, name, prop.get("type"))
        py_type = _TYPE_MAP[json_type]
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
