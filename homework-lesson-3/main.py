"""Research Agent — interactive entry point.

Runs a REPL loop where the user types questions and the agent
autonomously searches the web, reads pages, and generates reports.
Conversation memory is maintained via a thread_id so the agent
remembers prior messages within the session.
"""

import uuid
import logging

from langchain_core.messages import HumanMessage

from agent import agent
from config import Settings

# Configure logging — suppress all library noise (httpx, primp, trafilatura, etc.)
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = Settings()

# Unique thread_id per session for MemorySaver checkpointer
THREAD_CONFIG = {
    "configurable": {"thread_id": uuid.uuid4().hex},
    "recursion_limit": settings.max_iterations,
}


def main() -> None:
    """Interactive REPL for the Research Agent."""
    print("=" * 50)
    print("  Research Agent")
    print("  Type your question and press Enter.")
    print("  Commands: 'exit' / 'quit' to leave,")
    print("            'new' to start a fresh conversation.")
    print("=" * 50)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        if user_input.lower() == "new":
            THREAD_CONFIG["configurable"]["thread_id"] = uuid.uuid4().hex
            print("--- New conversation started ---")
            continue

        logger.info("User query: %s", user_input)

        try:
            for chunk in agent.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=THREAD_CONFIG,
                stream_mode="updates",
            ):
                # Process agent node updates
                if "agent" in chunk:
                    for msg in chunk["agent"].get("messages", []):
                        # Show tool calls being made
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                args_preview = list(tc["args"].values())[0] if tc["args"] else ""
                                print(f"\n  🔧 [{tc['name']}] {args_preview}")
                        # Print final text responses (skip tool call messages)
                        elif hasattr(msg, "content") and msg.content:
                            print(f"\nAgent: {msg.content}")

                # Show tool execution feedback
                if "tools" in chunk:
                    for msg in chunk["tools"].get("messages", []):
                        tool_name = getattr(msg, "name", "tool")
                        content_len = len(str(msg.content))
                        print(f"  ✅ [{tool_name}] → {content_len} chars")

        except KeyboardInterrupt:
            print("\n--- Interrupted. You can continue or type 'exit'. ---")
        except Exception as e:
            logger.error("Agent error: %s", e, exc_info=True)
            print(f"\nError: {e}\nPlease try again or rephrase your question.")


if __name__ == "__main__":
    main()
