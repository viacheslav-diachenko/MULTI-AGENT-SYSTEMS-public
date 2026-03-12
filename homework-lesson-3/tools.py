"""Research Agent tools.

Each tool is decorated with @tool so LangChain can automatically generate
the JSON Schema for tool calling. Tools handle their own errors and return
human-readable messages on failure.
"""

import os
import logging
from typing import Optional

import trafilatura
from ddgs import DDGS
from langchain_core.tools import tool

from config import Settings

logger = logging.getLogger(__name__)
settings = Settings()


@tool
def web_search(query: str, max_results: Optional[int] = None) -> str:
    """Search the internet using DuckDuckGo.

    Returns a list of search results with titles, URLs, and short snippets.
    Use this tool to discover relevant web pages for your research.

    Args:
        query: The search query string.
        max_results: Number of results to return (default from settings).
    """
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


@tool
def read_url(url: str) -> str:
    """Fetch and extract the main text content from a web page.

    Use this tool when you need the full text of an article found via
    web_search. The result is truncated to fit within context limits.

    Args:
        url: The full URL of the web page to read.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as e:
        logger.warning("read_url fetch failed for url=%r: %s", url, e)
        return f"Failed to fetch URL: {e}"

    if downloaded is None:
        return f"Could not download content from {url}. The page may be unavailable or blocking automated access."

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

    # Context engineering: truncate to limit
    max_len = settings.max_url_content_length
    if len(text) > max_len:
        text = text[:max_len] + f"\n\n[... TRUNCATED — showing first {max_len} of {len(text)} characters]"

    return text


@tool
def write_report(filename: str, content: str) -> str:
    """Save a Markdown report to a file.

    Use this tool to save your final research report. The file will be
    created in the output directory.

    Args:
        filename: Name of the file (e.g. 'rag_comparison.md').
        content: The full Markdown content of the report.
    """
    # Sanitize filename
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
