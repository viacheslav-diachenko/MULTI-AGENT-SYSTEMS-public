"""Research Agent tools.

Includes web tools from hw3 + RAG knowledge_search tool.
"""

import os
import logging
from typing import Optional

import trafilatura
from ddgs import DDGS
from langchain_core.tools import tool

from config import Settings
from retriever import get_retriever

logger = logging.getLogger(__name__)
settings = Settings()

# Initialize hybrid retriever (loads FAISS + BM25 from disk)
_retriever = get_retriever()


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

    You can narrow results by source file or page number using optional filters.

    Args:
        query: The search query string.
        source_filter: Optional filename substring to filter results
            (e.g. "langchain" matches "langchain.pdf").
        page_filter: Optional page number to filter results (0-indexed).
    """
    try:
        docs = _retriever.invoke(query)
    except Exception as e:
        logger.warning("knowledge_search failed: %s", e)
        return f"Knowledge base search failed: {e}"

    if not docs:
        return "No relevant documents found in the knowledge base. Try web_search instead."

    # Apply metadata filters (post-retrieval)
    if source_filter:
        source_lower = source_filter.lower()
        docs = [
            d for d in docs
            if source_lower in os.path.basename(d.metadata.get("source", "")).lower()
        ]
    if page_filter is not None:
        docs = [d for d in docs if d.metadata.get("page") == page_filter]

    if not docs:
        return (
            f"No results after filtering (source={source_filter!r}, page={page_filter}). "
            "Try a broader query or remove filters."
        )

    results = []
    for i, doc in enumerate(docs, 1):
        source = os.path.basename(doc.metadata.get("source", "unknown"))
        page = doc.metadata.get("page", "?")
        score = doc.metadata.get("rerank_score", "n/a")
        results.append(f"[{i}] Source: {source}, Page {page} (score: {score})\n{doc.page_content}")

    output = "\n\n---\n\n".join(results)

    # Context engineering: truncate knowledge search results
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
def write_report(filename: str, content: str) -> str:
    """Save a Markdown report to a file.

    Use this tool to save your final research report. The file will be
    created in the output directory.

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
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        logger.error("write_report failed for path=%r: %s", filepath, e)
        return f"Failed to save report: {e}"

    return f"Report saved successfully: {os.path.abspath(filepath)}"
