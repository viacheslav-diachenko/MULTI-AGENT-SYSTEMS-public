"""Research Agent tools.

Plain Python functions (no framework decorators) with JSON Schema definitions
for the OpenAI function calling API. Each tool handles its own errors and
returns human-readable messages on failure.
"""

import os
import logging
from typing import Optional

import trafilatura
from ddgs import DDGS

from config import Settings

logger = logging.getLogger(__name__)
settings = Settings()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: Optional[int] = None) -> str:
    """Search the internet using DuckDuckGo."""
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

    return "\n\n".join(formatted)


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


# ---------------------------------------------------------------------------
# JSON Schema definitions (OpenAI function calling format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet using DuckDuckGo. "
                "Returns a list of search results with titles, URLs, "
                "and short snippets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": (
                            "Number of results to return (default: 5)."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": (
                "Fetch and extract the main text content from a web page. "
                "Use this when you need the full text of an article found "
                "via web_search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the web page to read.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_report",
            "description": (
                "Save a Markdown report to a file in the output directory. "
                "Use ONLY when the user explicitly asks to save a report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": (
                            "Name of the file (e.g. 'rag_comparison.md')."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "The full Markdown content of the report."
                        ),
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Registry: tool name -> callable
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, callable] = {
    "web_search": web_search,
    "read_url": read_url,
    "write_report": write_report,
}
