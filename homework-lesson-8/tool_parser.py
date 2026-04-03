"""XML tool call parser for Qwen3-style models.

Some LLM backends (e.g. sglang) don't parse tool calls into the OpenAI
function calling format. Instead, the model outputs XML in the content:

    <tool_call>
    <function=web_search>
    <parameter=query>LangGraph framework</parameter>
    </function>
    </tool_call>

This module wraps a ChatModel to intercept responses, parse XML tool calls,
and convert them into proper AIMessage.tool_calls format that LangGraph
create_react_agent expects.
"""

import re
import uuid
import logging
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

# Regex to match one <tool_call>...</tool_call> block
_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=(\w+)>(.*?)</function>\s*</tool_call>",
    re.DOTALL,
)

# Regex to match <parameter=name>value</parameter> within a function block
_PARAM_RE = re.compile(
    r"<parameter=(\w+)>\s*(.*?)\s*</parameter>",
    re.DOTALL,
)


def parse_xml_tool_calls(content: str) -> tuple[str, list[dict]]:
    """Parse Qwen3 XML tool calls from message content.

    Returns:
        Tuple of (remaining_text, list_of_tool_calls) where each tool call
        is a dict with 'name', 'args', and 'id' keys.
    """
    tool_calls = []
    for match in _TOOL_CALL_RE.finditer(content):
        func_name = match.group(1)
        params_block = match.group(2)

        args = {}
        for param_match in _PARAM_RE.finditer(params_block):
            param_name = param_match.group(1)
            param_value = param_match.group(2).strip()
            # Try to parse numeric values
            if param_value.isdigit():
                args[param_name] = int(param_value)
            else:
                args[param_name] = param_value

        tool_calls.append({
            "name": func_name,
            "args": args,
            "id": f"call_{uuid.uuid4().hex[:12]}",
        })

    # Remove tool call XML from the text content
    remaining = _TOOL_CALL_RE.sub("", content).strip()
    return remaining, tool_calls


class Qwen3ChatWrapper(BaseChatModel):
    """Wrapper that intercepts XML tool calls from Qwen3 models.

    Delegates to the underlying ChatModel, then post-processes the response
    to convert XML tool calls into proper AIMessage.tool_calls format.
    """

    delegate: BaseChatModel
    _bound_tool_schemas: list[dict] = []

    @property
    def _llm_type(self) -> str:
        return "qwen3-xml-wrapper"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Inject stored tool schemas into kwargs so they appear in the API request
        if self._bound_tool_schemas and "tools" not in kwargs:
            kwargs["tools"] = self._bound_tool_schemas

        # Call the underlying model
        result = self.delegate._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        # Post-process each generation
        new_generations = []
        for gen in result.generations:
            msg = gen.message
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                remaining, tool_calls = parse_xml_tool_calls(msg.content)
                if tool_calls:
                    logger.info(
                        "Parsed %d XML tool call(s): %s",
                        len(tool_calls),
                        [tc["name"] for tc in tool_calls],
                    )
                    new_msg = AIMessage(
                        content=remaining,
                        tool_calls=tool_calls,
                        response_metadata=msg.response_metadata,
                    )
                    new_generations.append(ChatGeneration(message=new_msg))
                    continue
            new_generations.append(gen)

        return ChatResult(generations=new_generations, llm_output=result.llm_output)

    def bind_tools(self, tools: list, **kwargs: Any) -> "Qwen3ChatWrapper":
        """Store tool schemas for injection into API requests.

        Instead of using delegate.bind_tools() (which returns a
        RunnableBinding, not a BaseChatModel), we store the schemas
        and inject them in _generate() kwargs. The model sees the tool
        definitions in the API request and outputs XML tool calls.
        """
        from langchain_core.utils.function_calling import convert_to_openai_tool

        schemas = []
        for t in tools:
            if isinstance(t, dict):
                schemas.append(t)
            else:
                schemas.append(convert_to_openai_tool(t))

        new_wrapper = Qwen3ChatWrapper(delegate=self.delegate)
        new_wrapper._bound_tool_schemas = schemas
        return new_wrapper

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"delegate": self.delegate._identifying_params}
