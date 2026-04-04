"""Planner Agent — decomposes user requests into structured research plans.

Uses web_search and knowledge_search for preliminary domain exploration,
then returns a structured ResearchPlan via response_format.
"""

import logging

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Settings, get_planner_prompt
from schemas import ResearchPlan
from tool_parser import Qwen3ChatWrapper
from tools import knowledge_search, web_search

logger = logging.getLogger(__name__)


def build_planner_agent():
    """Create a fresh Planner agent with a dynamic prompt."""
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
        tools=[web_search, knowledge_search],
        system_prompt=get_planner_prompt(),
        response_format=ResearchPlan,
    )
