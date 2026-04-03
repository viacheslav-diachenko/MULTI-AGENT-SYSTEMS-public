"""Multi-agent research system — interactive entry point.

Runs a REPL loop where the user types questions and the Supervisor
orchestrates Plan -> Research -> Critique cycle. save_report operations
require user approval (approve / edit / reject).
"""

import json
import uuid
import logging

from langgraph.types import Command, Interrupt

from config import Settings
from supervisor import supervisor

# Configure logging — suppress library noise
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = Settings()

# Module-level config reference for use in handle_interrupt
_current_config: dict = {}


def print_interrupt(interrupt: Interrupt) -> None:
    """Display interrupt details for user review."""
    print(f"\n{'=' * 60}")
    print(f"  ACTION REQUIRES APPROVAL")
    print(f"{'=' * 60}")
    action_requests = interrupt.value.get("action_requests", [])
    for request in action_requests:
        action = request.get("action", "N/A")
        args = request.get("args", {})
        print(f"  Tool:     {action}")
        filename = args.get("filename", "unknown")
        content = args.get("content", "")
        print(f"  Filename: {filename}")
        preview = content[:500]
        print(f"  Preview:\n{preview}")
        if len(content) > 500:
            print(f"  ... ({len(content)} characters total)")
    print(f"{'=' * 60}")


def handle_interrupt(interrupt: Interrupt) -> None:
    """Handle HITL interrupt: approve / edit / reject."""
    while True:
        try:
            decision = input("\n  approve / edit / reject: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            decision = "reject"

        if decision == "approve":
            print("\n  Approved! Saving report...")
            resume_value = {interrupt.id: {"decisions": [{"type": "approve"}]}}
            for step in supervisor.stream(
                Command(resume=resume_value),
                config=_current_config,
                stream_mode="updates",
            ):
                process_stream_step(step)
            return

        elif decision == "edit":
            try:
                feedback = input("  Your feedback (what to change): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Cancelled.")
                return
            if not feedback:
                print("  No feedback provided. Try again.")
                continue
            print("\n  Sending feedback to Supervisor for revision...")
            resume_value = {
                interrupt.id: {
                    "decisions": [
                        {
                            "type": "edit",
                            "edited_action": {"feedback": feedback},
                        }
                    ]
                }
            }
            for step in supervisor.stream(
                Command(resume=resume_value),
                config=_current_config,
                stream_mode="updates",
            ):
                process_stream_step(step)
            return

        elif decision == "reject":
            print("\n  Rejected. Report will not be saved.")
            resume_value = {
                interrupt.id: {
                    "decisions": [{"type": "reject", "message": "User cancelled"}]
                }
            }
            for step in supervisor.stream(
                Command(resume=resume_value),
                config=_current_config,
                stream_mode="updates",
            ):
                process_stream_step(step)
            return

        else:
            print("  Invalid choice. Please enter: approve, edit, or reject")


def process_stream_step(step: dict) -> None:
    """Process a single stream step — print messages or handle interrupts."""
    for key, update in step.items():
        # Handle interrupts (HITL)
        if isinstance(update, tuple) and len(update) > 0 and isinstance(update[0], Interrupt):
            interrupt = update[0]
            print_interrupt(interrupt)
            handle_interrupt(interrupt)
            return

        if not isinstance(update, dict):
            continue

        for msg in update.get("messages", []):
            # Show tool calls being made
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    args_preview = ""
                    if tc.get("args"):
                        first_val = list(tc["args"].values())[0]
                        args_preview = str(first_val)[:100]
                    print(f"\n  [Supervisor -> {tc['name']}] {args_preview}")

            # Show tool results
            elif hasattr(msg, "name") and getattr(msg, "type", "") == "tool":
                content_len = len(str(msg.content))
                print(f"  <- [{msg.name}] {content_len} chars")

            # Print final text responses (not tool messages)
            elif hasattr(msg, "content") and msg.content:
                msg_type = getattr(msg, "type", "")
                if msg_type not in ("tool",):
                    print(f"\nAgent: {msg.content}")


def main() -> None:
    """Interactive REPL for the multi-agent research system."""
    global _current_config

    print("=" * 60)
    print("  Multi-Agent Research System")
    print("  Supervisor + Planner + Researcher + Critic")
    print("  Type your research question and press Enter.")
    print("  Commands: 'exit'/'quit' to leave,")
    print("            'new' to start a fresh conversation.")
    print("=" * 60)

    thread_id = uuid.uuid4().hex
    _current_config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.max_iterations,
    }

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
            thread_id = uuid.uuid4().hex
            _current_config["configurable"]["thread_id"] = thread_id
            print("--- New conversation started ---")
            continue

        logger.info("User query: %s", user_input)

        try:
            for step in supervisor.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=_current_config,
                stream_mode="updates",
            ):
                process_stream_step(step)

        except KeyboardInterrupt:
            print("\n--- Interrupted. You can continue or type 'exit'. ---")
        except Exception as e:
            logger.error("Supervisor error: %s", e, exc_info=True)
            print(f"\nError: {e}\nPlease try again or rephrase your question.")


if __name__ == "__main__":
    main()
