"""Research Agent — interactive entry point.

Runs a REPL loop where the user types questions and the agent
autonomously searches the web, reads pages, and synthesizes answers.
Conversation memory is maintained as a plain list of messages
within the ResearchAgent instance.
"""

import logging

from agent import ResearchAgent
from config import Settings

# Suppress all library noise (httpx, primp, trafilatura, etc.)
logging.basicConfig(level=logging.CRITICAL)


def main() -> None:
    """Interactive REPL for the Research Agent."""
    settings = Settings()
    agent = ResearchAgent(settings)

    print("=" * 50)
    print("  Research Agent (Custom ReAct)")
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
            agent.reset()
            print("--- New conversation started ---")
            continue

        try:
            agent.chat(user_input)  # streaming prints tokens in real time
        except KeyboardInterrupt:
            print("\n--- Interrupted. You can continue or type 'exit'. ---")
        except Exception as e:
            print(f"\nError: {e}\nPlease try again or rephrase your question.")


if __name__ == "__main__":
    main()
