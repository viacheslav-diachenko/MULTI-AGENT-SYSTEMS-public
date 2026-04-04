"""Multi-agent research system — interactive entry point.

Runs a REPL loop where the user types questions and the Supervisor
orchestrates Plan -> Research -> Critique cycle. save_report operations
require user approval (approve / edit / revise / reject).
"""

import logging
import uuid

from langgraph.types import Command, Interrupt

from config import Settings
from supervisor import build_supervisor, reset_revision_counter

# Configure logging — suppress library noise
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = Settings()

# Module-level references for use in handle_interrupt
_current_config: dict = {}
_current_supervisor = None


def print_interrupt(interrupt: Interrupt) -> None:
    """Display interrupt details for user review."""
    print(f"\n{'=' * 60}")
    print("  ACTION REQUIRES APPROVAL")
    print(f"{'=' * 60}")
    action_requests = interrupt.value.get("action_requests", [])
    for request in action_requests:
        action = request.get("action") or request.get("name") or "N/A"
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


def _resume_supervisor(resume_value: dict) -> None:
    """Resume the supervisor graph after an interrupt."""
    if _current_supervisor is None:
        raise RuntimeError("No active supervisor run to resume.")

    for step in _current_supervisor.stream(
        Command(resume=resume_value),
        config=_current_config,
        stream_mode="updates",
    ):
        process_stream_step(step)


def _prompt_replacement_content(current_content: str) -> str | None:
    """Prompt for full replacement content; blank first line keeps current content."""
    print("  Replacement content editor:")
    print("    - Press Enter on an empty first line to keep the current content.")
    print("    - Otherwise paste the full replacement Markdown.")
    print("    - Finish the paste with a line containing only END.")

    try:
        first_line = input()
    except (EOFError, KeyboardInterrupt):
        return None

    if first_line == "":
        return current_content

    lines = [first_line]
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            return None
        if line == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def handle_interrupt(interrupt: Interrupt) -> None:
    """Handle HITL interrupt: approve / edit / revise / reject.

    approve
        Execute the tool call as-is.
    edit
        Modify tool-call args directly before execution.
    revise
        Send feedback back to the Supervisor so it rewrites the report.
    reject
        Cancel saving entirely.
    """
    action_requests = interrupt.value.get("action_requests", [])
    original_action = action_requests[0] if action_requests else {}
    original_args = original_action.get("args", {})

    while True:
        try:
            decision = input("\n  approve / edit / revise / reject: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            decision = "reject"

        if decision == "approve":
            print("\n  Approved! Saving report...")
            _resume_supervisor({"decisions": [{"type": "approve"}]})
            return

        if decision == "edit":
            if not original_action:
                print("  No action request available to edit.")
                continue

            action_name = original_action.get("action") or original_action.get("name") or "save_report"
            current_filename = original_args.get("filename", "report.md")
            current_content = original_args.get("content", "")

            try:
                new_filename = input(
                    f"  New filename (Enter to keep '{current_filename}'): "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Edit cancelled. Returning to approval prompt.")
                continue

            new_content = _prompt_replacement_content(current_content)
            if new_content is None:
                print("\n  Edit cancelled. Returning to approval prompt.")
                continue

            edited_action = {
                "name": action_name,
                "args": {
                    "filename": new_filename or current_filename,
                    "content": new_content,
                },
            }
            print("\n  Applying edited tool arguments...")
            _resume_supervisor({
                "decisions": [
                    {"type": "edit", "editedAction": edited_action},
                ]
            })
            return

        if decision == "revise":
            try:
                feedback = input("  Your feedback (what to change): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Revision feedback cancelled. Returning to approval prompt.")
                continue
            if not feedback:
                print("  No feedback provided. Try again.")
                continue
            print("\n  Sending feedback to Supervisor for revision...")
            _resume_supervisor({
                "decisions": [
                    {"type": "reject", "message": f"User feedback: {feedback}"},
                ]
            })
            return

        if decision == "reject":
            print("\n  Rejected. Report will not be saved.")
            _resume_supervisor({
                "decisions": [
                    {"type": "reject", "message": "User cancelled the report."},
                ]
            })
            return

        print("  Invalid choice. Please enter: approve, edit, revise, or reject")


def process_stream_step(step: dict) -> None:
    """Process a single stream step — print messages or handle interrupts."""
    for _, update in step.items():
        if isinstance(update, tuple) and len(update) > 0 and isinstance(update[0], Interrupt):
            interrupt = update[0]
            print_interrupt(interrupt)
            handle_interrupt(interrupt)
            return

        if not isinstance(update, dict):
            continue

        for msg in update.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    args_preview = ""
                    if tool_call.get("args"):
                        first_val = list(tool_call["args"].values())[0]
                        args_preview = str(first_val)[:100]
                    print(f"\n  [Supervisor -> {tool_call['name']}] {args_preview}")

            elif hasattr(msg, "name") and getattr(msg, "type", "") == "tool":
                content_len = len(str(msg.content))
                print(f"  <- [{msg.name}] {content_len} chars")

            elif hasattr(msg, "content") and msg.content:
                msg_type = getattr(msg, "type", "")
                if msg_type not in ("tool",):
                    print(f"\nAgent: {msg.content}")


def main() -> None:
    """Interactive REPL for the multi-agent research system."""
    global _current_config, _current_supervisor

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
            _current_supervisor = None
            print("--- New conversation started ---")
            continue

        logger.info("User query: %s", user_input)
        reset_revision_counter(thread_id)
        _current_supervisor = build_supervisor()

        try:
            for step in _current_supervisor.stream(
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
