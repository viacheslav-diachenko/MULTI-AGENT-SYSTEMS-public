"""Research Agent with a custom ReAct loop and streaming output.

Replaces LangGraph's create_react_agent with a hand-rolled loop that:
- Streams responses from the OpenAI-compatible API with tool definitions
- Parses tool calls from the response (native or XML fallback for Qwen3)
- Executes tools and appends results to the conversation
- Enforces tool call budget and duplicate protection
- Repeats until the model produces a final text answer or the budget is hit

No LangGraph, no LangChain — just the openai SDK and plain Python.
"""

import json
import re
import sys
import uuid
import logging
from dataclasses import dataclass, field

import openai

from config import SYSTEM_PROMPT, Settings
from tools import TOOL_REGISTRY, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

# Tag that signals the start of an XML tool call in streamed content.
# Used to suppress printing raw XML to stdout.
_XML_TOOL_TAG = "<tool_call>"


# ---------------------------------------------------------------------------
# XML tool call parser (Qwen3 fallback)
# ---------------------------------------------------------------------------

_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=(\w+)>(.*?)</function>\s*</tool_call>",
    re.DOTALL,
)

_PARAM_RE = re.compile(
    r"<parameter=(\w+)>\s*(.*?)\s*</parameter>",
    re.DOTALL,
)


def parse_xml_tool_calls(content: str) -> tuple[str, list[dict]]:
    """Parse Qwen3 XML tool calls from message content."""
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
# Streaming accumulator
# ---------------------------------------------------------------------------

@dataclass
class _ToolCallAccumulator:
    """Accumulates streamed tool call deltas into a complete tool call."""
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class _StreamResult:
    """Result of consuming one full streamed response."""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Research Agent
# ---------------------------------------------------------------------------

class ResearchAgent:
    """ReAct agent with streaming output.

    The agent maintains a conversation history (list of dicts in OpenAI
    message format) and uses a while-loop to implement the
    Thought-Action-Observation cycle with real-time token streaming.
    """

    def __init__(self, settings: Settings) -> None:
        self.client = openai.OpenAI(
            base_url=settings.api_base,
            api_key=settings.api_key.get_secret_value(),
        )
        self.model = settings.model_name
        self.temperature = settings.temperature
        self.max_iterations = settings.max_iterations
        self.max_tool_calls = settings.max_tool_calls
        self.messages: list[dict] = []

    def reset(self) -> None:
        """Clear conversation history (start a new thread)."""
        self.messages.clear()

    def chat(self, user_input: str) -> str:
        """Process a user message through the ReAct loop with streaming.

        Enforces a hard tool call budget and duplicate call protection.
        Returns the final text answer.
        """
        self.messages.append({"role": "user", "content": user_input})

        tool_call_count = 0
        seen_calls: set[str] = set()  # "name:args_json" keys for duplicate detection

        for iteration in range(self.max_iterations):
            logger.debug("ReAct iteration %d/%d", iteration + 1, self.max_iterations)

            result = self._stream_llm()
            tool_calls = result.tool_calls

            # Check XML fallback if no native tool calls
            if not tool_calls and result.content:
                _, xml_calls = parse_xml_tool_calls(result.content)
                if xml_calls:
                    logger.info(
                        "Parsed %d XML tool call(s): %s",
                        len(xml_calls),
                        [tc["name"] for tc in xml_calls],
                    )
                    tool_calls = xml_calls

            if not tool_calls:
                # Final answer — no more tool calls
                content = result.content
                if not content:
                    content = _TOOL_CALL_RE.sub("", result.content).strip()
                self.messages.append({"role": "assistant", "content": content})
                return content

            # --- Budget check: stop if tool call limit reached ---
            if tool_call_count + len(tool_calls) > self.max_tool_calls:
                logger.warning(
                    "Tool call budget exhausted (%d/%d), forcing final answer",
                    tool_call_count, self.max_tool_calls,
                )
                break

            # Append assistant message with tool_calls to history
            # Strip XML tags from content if XML-parsed
            display_content = result.content
            if not result.tool_calls and display_content:
                display_content, _ = parse_xml_tool_calls(display_content)

            self.messages.append({
                "role": "assistant",
                "content": display_content,
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

            # Execute each tool call (with duplicate detection)
            for tc in tool_calls:
                name = tc["name"]
                args = tc["args"]
                call_id = tc["id"]

                # --- Duplicate detection ---
                call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                if call_key in seen_calls:
                    logger.info("Skipping duplicate tool call: %s", call_key)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": (
                            f"Duplicate call skipped — you already called "
                            f"{name} with these exact arguments. "
                            "Use the previous result or try different arguments."
                        ),
                    })
                    continue

                seen_calls.add(call_key)
                tool_call_count += 1

                args_preview = next(
                    (v for v in args.values() if isinstance(v, str)), ""
                )
                print(f"\n  \U0001f527 [{name}] {args_preview}")

                result_str = self._execute_tool(name, args)
                print(
                    f"  \u2705 [{name}] \u2192 {len(result_str)} chars"
                    f"  ({tool_call_count}/{self.max_tool_calls})"
                )

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": result_str,
                })

        # Budget or iteration limit reached — force final answer
        logger.warning(
            "Forcing final answer (tool calls: %d/%d, iterations: %d/%d)",
            tool_call_count, self.max_tool_calls,
            iteration + 1, self.max_iterations,
        )
        self.messages.append({
            "role": "user",
            "content": (
                "You have reached the maximum number of tool calls. "
                "Please provide your final answer now based on the "
                "information gathered so far."
            ),
        })

        final = self._stream_llm()
        content = final.content or (
            "I was unable to complete the research within the tool call budget."
        )
        self.messages.append({"role": "assistant", "content": content})
        return content

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def _stream_llm(self) -> _StreamResult:
        """Stream a response from the LLM, printing tokens in real time.

        Buffers content that looks like XML tool calls (Qwen3 fallback) to
        prevent raw ``<tool_call>`` tags from leaking to stdout. Text before
        the first XML tag is printed immediately for real-time UX.

        Returns the fully accumulated _StreamResult with content and tool_calls.
        """
        request_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ] + self.messages

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=request_messages,
            tools=TOOL_SCHEMAS,
            temperature=self.temperature,
            stream=True,
        )

        content_parts: list[str] = []
        tc_accumulators: dict[int, _ToolCallAccumulator] = {}
        started_text = False
        xml_buffering = False  # True once we detect <tool_call> in stream

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # --- stream text content ---
            if delta.content:
                content_parts.append(delta.content)

                # Check if we've entered XML tool call territory
                if not xml_buffering:
                    accumulated = "".join(content_parts)
                    if _XML_TOOL_TAG in accumulated:
                        # Print only the text before the XML tag
                        pre_xml = accumulated.split(_XML_TOOL_TAG, 1)[0].strip()
                        if pre_xml and not started_text:
                            sys.stdout.write("\nAgent: " + pre_xml)
                            sys.stdout.flush()
                            started_text = True
                        xml_buffering = True
                    else:
                        # Safe to print — no XML detected yet
                        if not started_text:
                            sys.stdout.write("\nAgent: ")
                            started_text = True
                        sys.stdout.write(delta.content)
                        sys.stdout.flush()
                # If xml_buffering is True, we silently accumulate (no print)

            # --- accumulate tool call deltas ---
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_accumulators:
                        tc_accumulators[idx] = _ToolCallAccumulator()
                    acc = tc_accumulators[idx]
                    if tc_delta.id:
                        acc.id = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc.name = tc_delta.function.name
                        if tc_delta.function.arguments:
                            acc.arguments += tc_delta.function.arguments

        if started_text:
            sys.stdout.write("\n")
            sys.stdout.flush()

        # Build result
        result = _StreamResult(content="".join(content_parts))

        for idx in sorted(tc_accumulators):
            acc = tc_accumulators[idx]
            try:
                args = json.loads(acc.arguments) if acc.arguments else {}
            except json.JSONDecodeError:
                args = {}
            result.tool_calls.append({
                "name": acc.name,
                "args": args,
                "id": acc.id or f"call_{uuid.uuid4().hex[:12]}",
            })

        return result

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

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
