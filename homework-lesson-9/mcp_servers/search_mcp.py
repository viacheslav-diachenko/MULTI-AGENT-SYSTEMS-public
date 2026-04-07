"""SearchMCP — FastMCP server exposing research tools.

Tools:
    - web_search      — DuckDuckGo
    - read_url        — trafilatura article extraction
    - knowledge_search — hybrid retrieval over the local knowledge base

Resources:
    - resource://knowledge-base-stats — document count + last-updated timestamp

Run standalone:
    python mcp_servers/search_mcp.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Optional

# Allow running as "python mcp_servers/search_mcp.py" from the hw9 root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trafilatura
from ddgs import DDGS
from fastmcp import FastMCP

from config import Settings
from retriever import get_retriever

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

settings = Settings()
mcp = FastMCP(name="SearchMCP")

# Lazy retriever — build on first knowledge_search call so start-up stays fast.
_retriever = None


def _get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = get_retriever()
    return _retriever


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
def web_search(query: str, max_results: Optional[int] = None) -> str:
    """Search the web via DuckDuckGo. Returns ranked results with titles, URLs, snippets."""
    limit = max_results or settings.max_search_results
    try:
        results = DDGS().text(query, max_results=limit)
    except Exception as e:
        logger.warning("web_search failed: %s", e)
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
    max_len = settings.max_search_content_length
    if len(output) > max_len:
        output = output[:max_len] + (
            f"\n\n[... TRUNCATED — first {max_len} of {len(output)} chars]"
        )
    return output


@mcp.tool
def read_url(url: str) -> str:
    """Fetch a web page and extract its main text content (truncated)."""
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as e:
        logger.warning("read_url fetch failed: %s", e)
        return f"Failed to fetch URL: {e}"

    if downloaded is None:
        return f"Could not download content from {url}."

    try:
        text = trafilatura.extract(
            downloaded, include_links=True, include_tables=True, favor_recall=True,
        )
    except Exception as e:
        logger.warning("read_url extraction failed: %s", e)
        return f"Failed to extract text from {url}: {e}"

    if not text:
        return f"No readable text content found at {url}."

    max_len = settings.max_url_content_length
    if len(text) > max_len:
        text = text[:max_len] + f"\n\n[... TRUNCATED — first {max_len} of {len(text)} chars]"
    return text


@mcp.tool
def knowledge_search(
    query: str,
    source_filter: Optional[str] = None,
    page_filter: Optional[int] = None,
) -> str:
    """Hybrid search over the local knowledge base (RAG/LLM/LangChain PDFs).

    Optional ``source_filter`` (filename substring) and ``page_filter``
    (0-indexed page number) are applied *before* the reranker.
    """
    has_filters = source_filter is not None or page_filter is not None
    try:
        retriever = _get_retriever()
        docs = retriever.search(
            query,
            source_filter=source_filter,
            page_filter=page_filter,
            rerank_top_n=settings.filtered_rerank_top_n if has_filters else None,
        )
    except Exception as e:
        logger.warning("knowledge_search failed: %s", e)
        return f"Knowledge base search failed: {e}"

    if not docs:
        if has_filters:
            return (
                f"No results after filtering (source={source_filter!r}, page={page_filter}). "
                "Try a broader query or remove filters."
            )
        return "No relevant documents found. Try web_search instead."

    results = []
    for i, doc in enumerate(docs, 1):
        source = os.path.basename(doc.metadata.get("source", "unknown"))
        page = doc.metadata.get("page", "?")
        score = doc.metadata.get("rerank_score", "n/a")
        results.append(f"[{i}] Source: {source}, Page {page} (score: {score})\n{doc.page_content}")

    output = "\n\n---\n\n".join(results)
    max_len = settings.max_knowledge_content_length
    if len(output) > max_len:
        output = output[:max_len] + (
            f"\n\n[... TRUNCATED — first {max_len} of {len(output)} chars]"
        )
    return output


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("resource://knowledge-base-stats")
def knowledge_base_stats() -> str:
    """Return counts and last-updated timestamps for the ingested KB."""
    index_dir = settings.index_dir
    bm25_path = os.path.join(index_dir, "bm25_chunks.json")

    stats: dict = {
        "index_dir": index_dir,
        "exists": os.path.exists(index_dir),
        "chunk_count": None,
        "last_updated": None,
        "source_files": [],
    }

    if os.path.exists(bm25_path):
        try:
            with open(bm25_path, "r", encoding="utf-8") as f:
                chunks = json.load(f)
            stats["chunk_count"] = len(chunks)
            sources = sorted({
                os.path.basename(c.get("metadata", {}).get("source", "unknown"))
                for c in chunks
            })
            stats["source_files"] = sources
            mtime = os.path.getmtime(bm25_path)
            stats["last_updated"] = datetime.fromtimestamp(mtime).isoformat()
        except Exception as e:  # pragma: no cover — defensive
            stats["error"] = f"Failed to read bm25_chunks.json: {e}"

    return json.dumps(stats, ensure_ascii=False, indent=2)


def main() -> None:  # pragma: no cover — entry point
    logger.info("Starting SearchMCP on %s:%d", settings.search_mcp_host, settings.search_mcp_port)
    mcp.run(
        transport="streamable-http",
        host=settings.search_mcp_host,
        port=settings.search_mcp_port,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
