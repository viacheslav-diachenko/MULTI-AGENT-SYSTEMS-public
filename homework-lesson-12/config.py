"""Application settings and dynamic prompt builders for all agents.

All configurable values are loaded from environment variables (.env file)
via Pydantic Settings. Prompt builder functions delegate to Langfuse
Prompt Management — the bodies live in the registry (label=production),
not in this file. Runtime values like ``current_datetime`` /
``max_revision_rounds`` are passed as compile-time template variables so
the stored prompt body stays stable across calls.
"""

from datetime import datetime
from pathlib import Path

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings
from langchain_openai import ChatOpenAI

from langfuse_setup import get_prompt_text

# Anchor relative paths and .env lookup to the hw8 project root so
# launching the agent from any cwd (tmux/pm2/service) still reads and
# writes files deterministically. Without this, both the .env file and
# DATA_DIR/INDEX_DIR/OUTPUT_DIR would resolve against the process cwd.
PROJECT_ROOT: Path = Path(__file__).resolve().parent


def _resolve_path(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return str(path)


class Settings(BaseSettings):
    """Multi-agent research system configuration."""

    # LLM connection
    api_key: SecretStr = SecretStr("not-needed")
    api_base: str = "http://localhost:8000/v1"
    model_name: str = "qwen3.5-35b-a3b"
    temperature: float = 0.3

    # Web search
    max_search_results: int = 5
    max_search_content_length: int = 4000
    max_url_content_length: int = 8000

    # RAG — Knowledge search
    max_knowledge_content_length: int = 6000

    # RAG — Embeddings (OpenAI-compatible API)
    embedding_api_key: SecretStr = SecretStr("not-needed")
    embedding_base_url: str = "http://localhost:7998/v1"
    embedding_model: str = "Qwen/Qwen3-Embedding-8B"

    # RAG — Reranker (Infinity API)
    reranker_url: str = "http://localhost:7997/rerank"

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
    max_iterations: int = 50
    max_revision_rounds: int = 2

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        # Tolerate LANGFUSE_* and other env vars handled elsewhere
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def _normalise_paths(self) -> "Settings":
        """Rewrite filesystem paths to absolute values anchored at PROJECT_ROOT."""
        for attr in ("data_dir", "index_dir", "output_dir"):
            value = getattr(self, attr)
            object.__setattr__(self, attr, _resolve_path(value))
        return self


def create_llm(settings: Settings | None = None) -> ChatOpenAI:
    """Create the shared LLM client for all agents.

    vLLM parses Qwen3 tool calls natively into the OpenAI format,
    so no XML wrapper is needed — plain ChatOpenAI works directly.
    """
    active_settings = settings or Settings()
    return ChatOpenAI(
        base_url=active_settings.api_base,
        api_key=active_settings.api_key.get_secret_value(),
        model=active_settings.model_name,
        temperature=active_settings.temperature,
    )


def get_supervisor_prompt(settings: Settings | None = None) -> str:
    """Fetch the Supervisor prompt from Langfuse, compiled with runtime values."""
    active_settings = settings or Settings()
    return get_prompt_text(
        "hw12/supervisor_system",
        max_revision_rounds=active_settings.max_revision_rounds,
        current_datetime=datetime.now().isoformat(),
    )


def get_planner_prompt() -> str:
    """Fetch the Planner prompt from Langfuse."""
    return get_prompt_text("hw12/planner_system")


def get_researcher_prompt() -> str:
    """Fetch the Researcher prompt from Langfuse."""
    return get_prompt_text("hw12/researcher_system")


def get_critic_prompt() -> str:
    """Fetch the Critic prompt from Langfuse, compiled with the current date."""
    return get_prompt_text(
        "hw12/critic_system",
        current_date=datetime.now().strftime("%Y-%m-%d"),
    )
