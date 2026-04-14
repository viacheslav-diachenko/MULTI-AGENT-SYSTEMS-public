"""Planner Agent — decomposes user requests into structured research plans.

Uses web_search and knowledge_search for preliminary domain exploration,
then returns a structured ResearchPlan via response_format.
"""

import logging

from langchain.agents import create_agent

from config import Settings, create_llm, get_planner_prompt
from schemas import ResearchPlan
from tools import knowledge_search, web_search

logger = logging.getLogger(__name__)


def build_planner_agent():
    """Create a fresh Planner agent with a dynamic prompt."""
    settings = Settings()
    return create_agent(
        create_llm(settings),
        tools=[web_search, knowledge_search],
        system_prompt=get_planner_prompt(),
        response_format=ResearchPlan,
    )
