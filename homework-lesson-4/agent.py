"""Research Agent with a custom ReAct loop.

Replaces LangGraph's create_react_agent with a hand-rolled loop that:
- Sends messages to the OpenAI-compatible API with tool definitions
- Parses tool calls from the response (native or XML fallback for Qwen3)
- Executes tools and appends results to the conversation
- Repeats until the model produces a final text answer or the iteration limit is hit

No LangGraph, no LangChain — just the openai SDK and plain Python.
"""

import json
import re
import uuid
import logging

import openai

from config import SYSTEM_PROMPT, Settings
from tools import TOOL_REGISTRY, TOOL_SCHEMAS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# XML tool call parser (ported from homework-lesson-3/tool_parser.py)
# ---------------------------------------------------------------------------
# Qwen3.5 via SGLang may output tool calls as XML in the content field
# instead of using the native OpenAI tool_calls format.

_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=(\w+)>(.*?)</function>\s*</tool_call>",
    re.DOTALL,
)

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
            if param_value.isdigit():
                args[param_name] = int(param_value)
            else:
                args[param_name] = param_value

        tool_calls.append({
            "name": func_name,
            "args": args,
            "id": f"call_{uuid.uuid4().hex[:12]}",
        })

    remaining = _TOOL_CALL_RE.sub("", content).strip()
    return remaining, tool_calls


# ---------------------------------------------------------------------------
# Research Agent
# ---------------------------------------------------------------------------

class ResearchAgent:
    """ReAct agent that autonomously searches the web and synthesizes answers.

    The agent maintains a conversation history (list of dicts in OpenAI
    message format) and uses a simple while-loop to implement the
    Thought-Action-Observation cycle.
    """

    def __init__(self, settings: Settings) -> None:
        self.client = openai.OpenAI(
            base_url=settings.api_base,
            api_key=settings.api_key.get_secret_value(),
        )
        self.model = settings.model_name
        self.temperature = settings.temperature
        self.max_iterations = settings.max_iterations
        self.messages: list[dict] = []

    def reset(self) -> None:
        """Clear conversation history (start a new thread)."""
        self.messages.clear()

    def chat(self, user_input: str) -> str:
        """Process a user message through the ReAct loop.

        Appends the user message to history, then loops:
        call LLM -> check for tool calls -> execute tools -> repeat.
        Returns the final text answer.
        """
        self.messages.append({"role": "user", "content": user_input})

        for iteration in range(self.max_iterations):
            logger.debug("ReAct iteration %d/%d", iteration + 1, self.max_iterations)

            response = self._call_llm()
            assistant_msg = response.choices[0].message

            tool_calls = self._extract_tool_calls(assistant_msg)

            if not tool_calls:
                # Final answer — no more tool calls
                content = assistant_msg.content or ""
                self.messages.append({"role": "assistant", "content": content})
                return content

            # Append assistant message with tool_calls to history
            self._append_assistant_with_tools(assistant_msg, tool_calls)

            # Execute each tool call
            for tc in tool_calls:
                name = tc["name"]
                args = tc["args"]
                call_id = tc["id"]

                # Log the tool call (same format as homework-lesson-3)
                args_preview = next(
                    (v for v in args.values() if isinstance(v, str)), ""
                )
                print(f"\n  \U0001f527 [{name}] {args_preview}")

                # Execute
                result = self._execute_tool(name, args)

                # Log the result
                print(f"  \u2705 [{name}] \u2192 {len(result)} chars")

                # Append tool result to history
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": result,
                })

        # Iteration limit reached — ask model to finalize
        logger.warning("Iteration limit (%d) reached, forcing final answer", self.max_iterations)
        self.messages.append({
            "role": "user",
            "content": (
                "You have reached the maximum number of tool calls. "
                "Please provide your final answer now based on the "
                "information gathered so far."
            ),
        })

        response = self._call_llm()
        content = response.choices[0].message.content or (
            "I was unable to complete the research within the iteration limit."
        )
        self.messages.append({"role": "assistant", "content": content})
        return content

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_llm(self) -> openai.types.chat.ChatCompletion:
        """Call the OpenAI-compatible API with the current conversation."""
        request_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ] + self.messages

        return self.client.chat.completions.create(
            model=self.model,
            messages=request_messages,
            tools=TOOL_SCHEMAS,
            temperature=self.temperature,
        )

    def _extract_tool_calls(self, message) -> list[dict]:
        """Extract tool calls from an assistant message.

        Checks native OpenAI tool_calls first, then falls back to
        parsing XML tool calls from the content (Qwen3/SGLang).
        """
        # 1. Native tool_calls from the API response
        if message.tool_calls:
            calls = []
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                calls.append({
                    "name": tc.function.name,
                    "args": args,
                    "id": tc.id,
                })
            return calls

        # 2. XML fallback — parse content for Qwen3-style tool calls
        if message.content:
            _remaining, xml_calls = parse_xml_tool_calls(message.content)
            if xml_calls:
                logger.info(
                    "Parsed %d XML tool call(s): %s",
                    len(xml_calls),
                    [tc["name"] for tc in xml_calls],
                )
                return xml_calls

        return []

    def _append_assistant_with_tools(
        self, message, tool_calls: list[dict]
    ) -> None:
        """Append the assistant message with tool_calls in OpenAI format."""
        # When XML-parsed, strip the XML tags from content
        content = message.content or ""
        if not message.tool_calls and content:
            content, _ = parse_xml_tool_calls(content)

        self.messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in tool_calls
            ],
        })

    def _execute_tool(self, name: str, args: dict) -> str:
        """Execute a tool by name. Returns result string. Never raises."""
        func = TOOL_REGISTRY.get(name)
        if func is None:
            return (
                f"Error: Unknown tool '{name}'. "
                f"Available tools: {list(TOOL_REGISTRY.keys())}"
            )
        try:
            return func(**args)
        except Exception as e:
            logger.error("Tool %s raised: %s", name, e, exc_info=True)
            return f"Error executing {name}: {e}"
