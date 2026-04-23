"""Research Agent — executes research plans using web and knowledge base tools.

Reuses the same tools from HW5 (web_search, read_url, knowledge_search)
but wrapped as a sub-agent via create_agent.
"""

import logging

from langchain.agents import create_agent

from config import Settings, create_llm, get_researcher_prompt
from tools import knowledge_search, read_url, web_search

logger = logging.getLogger(__name__)


def build_research_agent():
    """Create a fresh Research agent with a dynamic prompt."""
    settings = Settings()
    return create_agent(
        create_llm(settings),
        tools=[web_search, read_url, knowledge_search],
        system_prompt=get_researcher_prompt(),
    )
