"""Critic Agent — evaluates research findings via independent verification.

Uses the same search/read tools to independently verify claims,
then returns a structured CritiqueResult via response_format.
"""

import logging

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Settings, get_critic_prompt
from schemas import CritiqueResult
from tool_parser import Qwen3ChatWrapper
from tools import knowledge_search, read_url, web_search

logger = logging.getLogger(__name__)


def build_critic_agent():
    """Create a fresh Critic agent with a dynamic prompt."""
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
        system_prompt=get_critic_prompt(),
        response_format=CritiqueResult,
    )
