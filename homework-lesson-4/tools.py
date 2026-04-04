"""Research Agent tools.

Auto-generates OpenAI function calling schemas from type hints and docstrings.
Each tool is registered via the @tool decorator — no manual JSON required.
"""

import inspect
import os
import logging
from typing import Optional, Union, get_args, get_origin, get_type_hints

import trafilatura
from ddgs import DDGS

from config import Settings

logger = logging.getLogger(__name__)
settings = Settings()

# ---------------------------------------------------------------------------
# Auto-schema decorator
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, callable] = {}
TOOL_SCHEMAS: list[dict] = []

_PY_TYPE_TO_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _resolve_json_type(annotation: type) -> str:
    """Resolve a Python type annotation to a JSON Schema type string.

    Handles Optional[T] (Union[T, None]) by extracting the inner type T.
    Falls back to "string" for unknown types.
    """
    # Unwrap Optional[T] → T (Optional[int] is Union[int, None])
    origin = get_origin(annotation)
    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if args:
            annotation = args[0]

    return _PY_TYPE_TO_JSON.get(annotation, "string")


def tool(func):
    """Register a function as an agent tool with auto-generated JSON schema."""
    hints = get_type_hints(func)
    sig = inspect.signature(func)

    properties = {}
    required = []

    for name, param in sig.parameters.items():
        json_type = _resolve_json_type(hints.get(name, str))
        properties[name] = {"type": json_type, "description": name}
        if param.default is inspect.Parameter.empty:
            required.append(name)

    schema = {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": inspect.getdoc(func) or "",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }

    TOOL_SCHEMAS.append(schema)
    TOOL_REGISTRY[func.__name__] = func
    return func


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

@tool
def web_search(query: str, max_results: Optional[int] = None) -> str:
    """Search the internet using DuckDuckGo. Returns titles, URLs, and snippets."""
    limit = max_results or settings.max_search_results
    try:
        results = DDGS().text(query, max_results=limit)
    except Exception as e:
        logger.warning("web_search failed for query=%r: %s", query, e)
        return f"Search failed: {e}. Try rephrasing the query."

    if not results:
        return "No results found. Try a different search query."

    formatted = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("href", r.get("link", ""))
        snippet = r.get("body", r.get("snippet", ""))
        formatted.append(f"{i}. **{title}**\n   URL: {url}\n   {snippet}")

    output = "\n\n".join(formatted)

    # Context engineering: truncate search results to prevent context overflow
    max_len = settings.max_search_content_length
    if len(output) > max_len:
        output = output[:max_len] + (
            f"\n\n[... TRUNCATED — showing first {max_len} of {len(output)} characters. "
            f"Use read_url on the most relevant URLs above for full content.]"
        )

    return output


@tool
def read_url(url: str) -> str:
    """Fetch and extract the main text content from a web page."""
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as e:
        logger.warning("read_url fetch failed for url=%r: %s", url, e)
        return f"Failed to fetch URL: {e}"

    if downloaded is None:
        return (
            f"Could not download content from {url}. "
            "The page may be unavailable or blocking automated access."
        )

    try:
        text = trafilatura.extract(
            downloaded,
            include_links=True,
            include_tables=True,
            favor_recall=True,
        )
    except Exception as e:
        logger.warning("read_url extraction failed for url=%r: %s", url, e)
        return f"Failed to extract text from {url}: {e}"

    if not text:
        return f"No readable text content found at {url}."

    max_len = settings.max_url_content_length
    if len(text) > max_len:
        text = (
            text[:max_len]
            + f"\n\n[... TRUNCATED — showing first {max_len} "
            f"of {len(text)} characters]"
        )

    return text


@tool
def write_report(filename: str, content: str) -> str:
    """Save a Markdown report to a file in the output directory."""
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    output_dir = settings.output_dir
    os.makedirs(output_dir, exist_ok=True)

    filepath = os.path.join(output_dir, safe_name)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        logger.error("write_report failed for path=%r: %s", filepath, e)
        return f"Failed to save report: {e}"

    abs_path = os.path.abspath(filepath)
    return f"Report saved successfully: {abs_path}"
