"""Research Agent — executes research plans using web and knowledge base tools.

Reuses the same tools from HW5 (web_search, read_url, knowledge_search)
but wrapped as a sub-agent via create_agent.
"""

import logging

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Settings, get_researcher_prompt
from tool_parser import Qwen3ChatWrapper
from tools import knowledge_search, read_url, web_search

logger = logging.getLogger(__name__)


def build_research_agent():
    """Create a fresh Research agent with a dynamic prompt."""
    settings = Settings()
    base_llm = ChatOpenAI(
        base_url=settings.api_base,
        api_key=settings.api_key.get_secret_value(),
        model=settings.model_name,
        temperature=settings.temperature,
    )
    llm = Qwen3ChatWrapper(delegate=base_llm)
    return create_agent(
        llm,
        tools=[web_search, read_url, knowledge_search],
        system_prompt=get_researcher_prompt(),
    )
