"""Research tools: web search, URL reading, knowledge search, and report saving.

Reused from homework-lesson-5 with write_report renamed to save_report
for clarity in the HITL context.
"""

import logging
import os
from typing import Optional

import trafilatura
from ddgs import DDGS
from langchain_core.tools import tool

from config import Settings
from retriever import get_retriever

logger = logging.getLogger(__name__)
settings = Settings()

# Lazy retriever — initialized on first knowledge_search call
_retriever = None


def _get_or_init_retriever():
    """Lazily initialize the hybrid retriever on first use."""
    global _retriever
    if _retriever is None:
        try:
            _retriever = get_retriever()
        except Exception as e:
            raise RuntimeError(
                f"Knowledge base not available: {e}. "
                "Run 'python ingest.py' first to build the index."
            ) from e
    return _retriever


@tool
def knowledge_search(
    query: str,
    source_filter: Optional[str] = None,
    page_filter: Optional[int] = None,
) -> str:
    """Search the local knowledge base about RAG, LLMs, and LangChain.

    The knowledge base contains these ingested PDF documents:
    - retrieval-augmented-generation.pdf — the original RAG paper
    - large-language-model.pdf — overview of LLM architectures
    - langchain.pdf — LangChain framework documentation

    Use this tool FIRST for questions about retrieval, embeddings, vector
    databases, chunking, reranking, LLM architectures, or LangChain.
    Use web_search instead for current events, recent developments (2025+),
    or topics not covered by the documents above.

    Args:
        query: The search query string.
        source_filter: Optional filename substring to filter results.
        page_filter: Optional page number to filter results (0-indexed).
    """
    has_filters = source_filter is not None or page_filter is not None

    try:
        retriever = _get_or_init_retriever()
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
        return "No relevant documents found in the knowledge base. Try web_search instead."

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
            f"\n\n[... TRUNCATED — showing first {max_len} of {len(output)} characters]"
        )

    return output


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
    for i, result in enumerate(results, 1):
        title = result.get("title", "No title")
        url = result.get("href", result.get("link", ""))
        snippet = result.get("body", result.get("snippet", ""))
        formatted.append(f"{i}. **{title}**\n   URL: {url}\n   {snippet}")

    output = "\n\n".join(formatted)

    max_len = settings.max_search_content_length
    if len(output) > max_len:
        output = output[:max_len] + (
            f"\n\n[... TRUNCATED — showing first {max_len} of {len(output)} characters. "
            f"Use read_url on the most relevant URLs above for full content.]"
        )

    return output


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
        return f"Could not download content from {url}."

    try:
        text = trafilatura.extract(
            downloaded, include_links=True, include_tables=True, favor_recall=True,
        )
    except Exception as e:
        logger.warning("read_url extraction failed for url=%r: %s", url, e)
        return f"Failed to extract text from {url}: {e}"

    if not text:
        return f"No readable text content found at {url}."

    max_len = settings.max_url_content_length
    if len(text) > max_len:
        text = text[:max_len] + f"\n\n[... TRUNCATED — first {max_len} of {len(text)} chars]"

    return text


@tool
def save_report(filename: str, content: str) -> str:
    """Save a Markdown report to a file.

    Use this tool to save the final research report after it has been
    approved by the Critic. The file will be created in the output directory.
    This operation requires user approval (HITL).

    Args:
        filename: Name of the file (e.g. 'rag_comparison.md').
        content: The full Markdown content of the report.
    """
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    output_dir = settings.output_dir
    os.makedirs(output_dir, exist_ok=True)

    filepath = os.path.join(output_dir, safe_name)
    try:
        with open(filepath, "w", encoding="utf-8") as file_handle:
            file_handle.write(content)
    except OSError as e:
        logger.error("save_report failed for path=%r: %s", filepath, e)
        return f"Failed to save report: {e}"

    return f"Report saved successfully: {os.path.abspath(filepath)}"
