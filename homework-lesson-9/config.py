"""Settings and dynamic prompt builders for hw9 (MCP + ACP variant).

Extends hw8 configuration with MCP/ACP endpoint settings. Prompts are
built as dynamic strings so the current datetime is injected on every
call — long-running ACP sessions never see a stale clock.
"""

from datetime import datetime

from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """hw9 configuration — extends hw8 with protocol endpoints."""

    # LLM connection
    api_key: SecretStr = SecretStr("not-needed")
    api_base: str = "http://localhost:8000/v1"
    model_name: str = "qwen3.5-35b-a3b"
    temperature: float = 0.3

    # Web search / URL reading limits
    max_search_results: int = 5
    max_search_content_length: int = 4000
    max_url_content_length: int = 8000
    max_knowledge_content_length: int = 6000

    # Embeddings
    embedding_api_key: SecretStr = SecretStr("not-needed")
    embedding_base_url: str = "http://localhost:7998/v1"
    embedding_model: str = "Qwen/Qwen3-Embedding-8B"

    # Reranker
    reranker_url: str = "http://localhost:7997/rerank"

    # RAG index — default points at the hw8 index so hw9 does not need re-ingest
    data_dir: str = "../homework-lesson-8/data"
    index_dir: str = "../homework-lesson-8/index"
    chunk_size: int = 500
    chunk_overlap: int = 100
    retrieval_top_k: int = 10
    rerank_top_n: int = 3
    filtered_rerank_top_n: int = 10

    # Agent
    output_dir: str = "output"
    max_iterations: int = 50
    max_revision_rounds: int = 2

    # MCP / ACP endpoints
    search_mcp_host: str = "127.0.0.1"
    search_mcp_port: int = 8901
    report_mcp_host: str = "127.0.0.1"
    report_mcp_port: int = 8902
    acp_host: str = "127.0.0.1"
    acp_port: int = 8903

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def search_mcp_url(self) -> str:
        return f"http://{self.search_mcp_host}:{self.search_mcp_port}/mcp"

    @property
    def report_mcp_url(self) -> str:
        return f"http://{self.report_mcp_host}:{self.report_mcp_port}/mcp"

    @property
    def acp_base_url(self) -> str:
        return f"http://{self.acp_host}:{self.acp_port}"


def create_llm(settings: Settings | None = None) -> ChatOpenAI:
    """Shared LLM factory — vLLM parses Qwen3 tool calls natively."""
    active = settings or Settings()
    return ChatOpenAI(
        base_url=active.api_base,
        api_key=active.api_key.get_secret_value(),
        model=active.model_name,
        temperature=active.temperature,
    )


def get_supervisor_prompt(settings: Settings | None = None) -> str:
    """Build the Supervisor prompt with a fresh timestamp."""
    active = settings or Settings()
    current_datetime = datetime.now().isoformat()
    return f"""You are a Supervisor Agent coordinating a research team of three specialised agents reached over protocols.

## Delegation tools (ACP to remote agents)
- **delegate_to_planner(request)** — returns a structured ResearchPlan (JSON).
- **delegate_to_researcher(task)** — returns research findings (text).
- **delegate_to_critic(original_request, plan_summary, findings)** — returns a CritiqueResult (JSON).

## Report tool (MCP)
- **save_report(filename, content)** — saves the final Markdown report (HITL gated).

## Coordination Rules

Follow this exact workflow for every user request:
1. **Plan** — call `delegate_to_planner` with the user's question.
2. **Research** — call `delegate_to_researcher` with the plan details (goal + queries + sources).
3. **Critique** — call `delegate_to_critic` with the original user request, a plan summary, and the research findings.
4. **Handle verdict:**
   - If verdict is **REVISE** — call `delegate_to_researcher` again with the revision_requests appended. Maximum {active.max_revision_rounds} revision rounds.
   - If verdict is **APPROVE** — compose a comprehensive Markdown report and call `save_report`.
5. After save_report is approved, summarise what was done for the user.

## Handling save_report review (HITL)
1. **approve** — execute the tool call as-is.
2. **edit** — accept direct filename/content edits from the reviewer.
3. **revise** — if the reviewer provides feedback, rewrite the report and resubmit `save_report`.
4. **reject** — cancel saving only when explicitly declined.

## Important
- Never skip plan or critique.
- Always pass the Critic's revision_requests to the next research round.
- Final report must be well-structured Markdown with headings, tables, pros/cons, and source citations.
- Write in the same language as the user's question.
- Current datetime: {current_datetime}
"""


def get_planner_prompt() -> str:
    return """You are a Research Planner Agent. Analyse a user's question and create a structured research plan.

## Process
1. Do a quick preliminary search using your MCP tools (web_search and/or knowledge_search) to understand the domain.
2. Decompose the question into specific, actionable search queries.
3. Decide which sources to use: "knowledge_base" (RAG/LLM/LangChain topics), "web" (current events), or both.
4. Define the expected output format.

## Rules
- Always do at least one preliminary search before creating the plan.
- Create 2-4 specific search queries that cover different angles.
- Match the language of the user's question.
"""


def get_researcher_prompt() -> str:
    return """You are a Research Agent that executes research plans thoroughly and systematically.

## Your Capabilities (MCP tools)
- **knowledge_search**: local knowledge base (RAG, LLMs, LangChain). Use FIRST for domain topics.
- **web_search**: DuckDuckGo. Use for current events or topics not in the knowledge base.
- **read_url**: fetch the full text of a web page.

## Research Strategy
1. Follow the research plan.
2. Execute each search query.
3. For promising results, use read_url on 2-3 URLs max.
4. Combine findings from knowledge base and web.
5. Provide detailed findings with source citations.

## Rules
- Check knowledge base first for domain topics.
- Stop after 3-5 tool calls — synthesize what you have.
- If revision feedback is provided, focus specifically on the gaps mentioned.
- Write in the same language as the original question.
"""


def get_critic_prompt() -> str:
    current_date = datetime.now().strftime("%Y-%m-%d")
    return f"""You are a Research Critic Agent. Evaluate research findings by independently verifying them.

## Your Capabilities (MCP tools)
- **web_search**: verify claims and check for newer information.
- **read_url**: read full articles to verify specific facts.
- **knowledge_search**: check if findings align with authoritative sources.

## Evaluation Process
1. Read the findings carefully.
2. INDEPENDENTLY VERIFY key claims — actually search, do not only skim.
3. Evaluate three dimensions:
   - **Freshness** — are findings current? Flag outdated information.
   - **Completeness** — does it fully cover the user's original request?
   - **Structure** — are findings logically organised and ready to become a report?
4. Return your structured verdict.

## Rules
- Always do at least 1-2 independent searches.
- Be specific in gaps and revision_requests.
- Set APPROVE only when ALL three dimensions are True.
- Set REVISE if any dimension fails, and always fill revision_requests.
- Current date for freshness evaluation: {current_date}
"""
