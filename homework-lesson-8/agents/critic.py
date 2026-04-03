"""Critic Agent — evaluates research findings via independent verification.

Uses the same search/read tools to independently verify claims,
then returns a structured CritiqueResult via response_format.
"""

import logging

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import CRITIC_PROMPT, Settings
from schemas import CritiqueResult
from tool_parser import Qwen3ChatWrapper
from tools import knowledge_search, read_url, web_search

logger = logging.getLogger(__name__)
settings = Settings()

_base_llm = ChatOpenAI(
    base_url=settings.api_base,
    api_key=settings.api_key.get_secret_value(),
    model=settings.model_name,
    temperature=settings.temperature,
)
_llm = Qwen3ChatWrapper(delegate=_base_llm)

critic_agent = create_agent(
    _llm,
    tools=[web_search, read_url, knowledge_search],
    system_prompt=CRITIC_PROMPT,
    response_format=CritiqueResult,
)
