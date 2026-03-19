"""Research Agent with RAG — assembly.

Creates a LangGraph ReAct agent with:
- ChatOpenAI pointed at sglang (Qwen3.5-35B-A3B)
- Qwen3ChatWrapper for XML tool call parsing
- Four tools: knowledge_search, web_search, read_url, write_report
- MemorySaver for conversational memory
"""

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from config import SYSTEM_PROMPT, Settings
from tool_parser import Qwen3ChatWrapper
from tools import knowledge_search, read_url, web_search, write_report

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
tools = [knowledge_search, web_search, read_url, write_report]

# Conversational memory — persists message history per thread_id
memory = MemorySaver()

# ReAct agent with system prompt and memory
agent = create_react_agent(
    model=llm,
    tools=tools,
    checkpointer=memory,
    prompt=SYSTEM_PROMPT,
)
