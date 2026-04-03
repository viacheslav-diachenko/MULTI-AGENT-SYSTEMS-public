"""Planner Agent — decomposes user requests into structured research plans.

Uses web_search and knowledge_search for preliminary domain exploration,
then returns a structured ResearchPlan via response_format.
"""

import logging

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import PLANNER_PROMPT, Settings
from schemas import ResearchPlan
from tool_parser import Qwen3ChatWrapper
from tools import knowledge_search, web_search

logger = logging.getLogger(__name__)
settings = Settings()

# LLM with Qwen3 XML tool call compatibility
_base_llm = ChatOpenAI(
    base_url=settings.api_base,
    api_key=settings.api_key.get_secret_value(),
    model=settings.model_name,
    temperature=settings.temperature,
)
_llm = Qwen3ChatWrapper(delegate=_base_llm)

planner_agent = create_agent(
    _llm,
    tools=[web_search, knowledge_search],
    system_prompt=PLANNER_PROMPT,
    response_format=ResearchPlan,
)
