"""Application settings and prompt configuration.

All configurable values are loaded from environment variables (.env file)
via Pydantic Settings.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Research Agent with RAG configuration."""

    # LLM connection
    api_key: SecretStr = SecretStr("not-needed")
    api_base: str = "http://10.43.67.254:8000/v1"
    model_name: str = "qwen3.5-35b-a3b"
    temperature: float = 0.3

    # Web search
    max_search_results: int = 5
    max_search_content_length: int = 4000
    max_url_content_length: int = 8000

    # RAG — Knowledge search
    max_knowledge_content_length: int = 6000

    # RAG — Embeddings (OpenAI-compatible API, e.g. TEI or OpenAI)
    embedding_api_key: SecretStr = SecretStr("not-needed")
    embedding_base_url: str = "http://10.43.45.148:7998/v1"
    embedding_model: str = "Qwen/Qwen3-Embedding-8B"

    # RAG — Reranker (Infinity API)
    reranker_url: str = "http://10.43.63.169:7997/rerank"

    # RAG — Index
    data_dir: str = "data"
    index_dir: str = "index"
    chunk_size: int = 500
    chunk_overlap: int = 100
    retrieval_top_k: int = 10
    rerank_top_n: int = 3
    filtered_rerank_top_n: int = 10

    # Agent
    output_dir: str = "output"
    max_iterations: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


SYSTEM_PROMPT = """You are a Research Agent with access to both the internet and a local knowledge base.

## Your Capabilities

You have access to the following tools:
- **knowledge_search**: Search the local knowledge base (ingested documents about RAG, LLMs, LangChain). \
Use this FIRST for questions about these topics.
- **web_search**: Search the internet via DuckDuckGo. Use for current events, recent developments, \
or topics not in the knowledge base.
- **read_url**: Fetch the full text of a web page for deeper analysis.
- **write_report**: Save a Markdown report to a file. Use ONLY when the user explicitly asks to save a report.

## Research Strategy

1. **Check knowledge base first** — use knowledge_search for domain topics \
(RAG, LLMs, retrieval, embeddings, LangChain).
2. **Supplement with web search** — use web_search for recent developments, comparisons, \
or topics not found locally.
3. **Read selectively** — pick 2-3 most relevant URLs from search results and read their full text.
4. **Synthesize** — combine findings from both sources into a comprehensive answer.

## Response Format

- Structured sections with Markdown headings
- Detailed explanations with pros/cons
- Comparison tables when relevant
- Source citations (both knowledge base and web)
- Write in the same language as the user's question

## Rules

- Always try knowledge_search before web_search for domain topics.
- Combine results from multiple sources for comprehensive answers.
- CRITICAL: Stop calling tools after 3-5 tool calls per question — synthesize and respond.
- Do NOT use write_report unless the user explicitly asks to save a file.
"""
