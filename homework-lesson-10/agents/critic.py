"""Critic Agent — evaluates research findings via independent verification.

Uses the same search/read tools to independently verify claims,
then returns a structured CritiqueResult via response_format.
"""

import logging

from langchain.agents import create_agent

from config import Settings, create_llm, get_critic_prompt
from schemas import CritiqueResult
from tools import knowledge_search, read_url, web_search

logger = logging.getLogger(__name__)


def build_critic_agent():
    """Create a fresh Critic agent with a dynamic prompt."""
    settings = Settings()
    return create_agent(
        create_llm(settings),
        tools=[web_search, read_url, knowledge_search],
        system_prompt=get_critic_prompt(),
        response_format=CritiqueResult,
    )
