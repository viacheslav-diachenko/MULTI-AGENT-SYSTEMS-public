"""Research Agent assembly.

Creates a LangGraph ReAct agent with:
- ChatOpenAI pointed at a local SGLang (OpenAI-compatible) endpoint
- Qwen3ChatWrapper to parse XML tool calls from Qwen3.5 models
- Three research tools (web_search, read_url, write_report)
- MemorySaver checkpointer for conversational memory across turns
"""

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from config import SYSTEM_PROMPT, Settings
from tool_parser import Qwen3ChatWrapper
from tools import read_url, web_search, write_report

settings = Settings()

# Base LLM — Qwen3.5 via sglang (OpenAI-compatible API)
_base_llm = ChatOpenAI(
    base_url=settings.api_base,
    api_key=settings.api_key.get_secret_value(),
    model=settings.model_name,
    temperature=settings.temperature,
)

# Wrap with XML tool call parser for sglang compatibility
llm = Qwen3ChatWrapper(delegate=_base_llm)

# Tools available to the agent
tools = [web_search, read_url, write_report]

# Conversational memory — persists message history per thread_id
memory = MemorySaver()

# ReAct agent with system prompt and memory
agent = create_react_agent(
    model=llm,
    tools=tools,
    checkpointer=memory,
    prompt=SYSTEM_PROMPT,
)
