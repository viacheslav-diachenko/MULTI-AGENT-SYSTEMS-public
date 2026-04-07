"""Interactive entry point for hw9 — Supervisor REPL with HITL gate.

Workflow:
    1. Start SearchMCP, ReportMCP, and the ACP server in separate processes.
    2. Run ``python main.py`` to open the REPL.
    3. Ask a research question; the Supervisor coordinates the three remote
       agents over ACP and stops on ``save_report`` for human review.

The HITL loop matches hw8: approve / edit / revise / reject.
"""

import logging
import uuid

from langgraph.types import Command, Interrupt

from config import Settings
from health import format_results, run_health_checks
from supervisor import (
    get_or_create_supervisor,
    reset_revision_counter,
    reset_thread,
)

logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = Settings()

_current_config: dict = {}
_current_supervisor = None


def print_interrupt(interrupt: Interrupt) -> None:
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
    if _current_supervisor is None:
        raise RuntimeError("No active supervisor run to resume.")
    for step in _current_supervisor.stream(
        Command(resume=resume_value),
        config=_current_config,
        stream_mode="updates",
    ):
        process_stream_step(step)


def _prompt_replacement_content(current_content: str) -> str | None:
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
    """approve / edit / revise / reject — same semantics as hw8."""
    action_requests = interrupt.value.get("action_requests", [])
    original_action = action_requests[0] if action_requests else {}
    original_args = original_action.get("args", {})

    while True:
        try:
            decision = input("\n  approve / edit / revise / reject: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            decision = "reject"

        if decision == "approve":
            print("\n  Approved! Saving report via ReportMCP...")
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
                print("\n  Edit cancelled.")
                continue

            new_content = _prompt_replacement_content(current_content)
            if new_content is None:
                print("\n  Edit cancelled.")
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
                "decisions": [{"type": "edit", "editedAction": edited_action}]
            })
            return

        if decision == "revise":
            try:
                feedback = input("  Your feedback (what to change): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Revision feedback cancelled.")
                continue
            if not feedback:
                print("  No feedback provided. Try again.")
                continue
            print("\n  Sending feedback to Supervisor for revision...")
            _resume_supervisor({
                "decisions": [{"type": "reject", "message": f"User feedback: {feedback}"}]
            })
            return

        if decision == "reject":
            print("\n  Rejected. Report will not be saved.")
            _resume_supervisor({
                "decisions": [{"type": "reject", "message": "User cancelled the report."}]
            })
            return

        print("  Invalid choice. Please enter: approve, edit, revise, or reject")


def process_stream_step(step: dict) -> None:
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
                content_str = str(msg.content)
                preview = content_str[:300].replace("\n", " ")
                suffix = "..." if len(content_str) > 300 else ""
                status = getattr(msg, "status", None)
                status_tag = f" [{status}]" if status and status != "success" else ""
                print(f"  <- [{msg.name}]{status_tag} ({len(content_str)} chars) {preview}{suffix}")

            elif hasattr(msg, "content") and msg.content:
                msg_type = getattr(msg, "type", "")
                if msg_type not in ("tool",):
                    print(f"\nAgent: {msg.content}")


def main() -> None:
    global _current_config, _current_supervisor

    print("=" * 60)
    print("  Multi-Agent Research System (hw9: MCP + ACP)")
    print("  Supervisor → ACP → (Planner | Researcher | Critic) → MCP")
    print("  Commands: 'exit'/'quit' to leave, 'new' to start a fresh conversation.")
    print("=" * 60)

    print("  Checking endpoints...")
    try:
        results = run_health_checks(settings)
    except Exception as exc:  # pragma: no cover — defensive
        print(f"  Health checks errored: {exc}")
        results = []
    if results:
        print(format_results(results))
        if any(not r.ok for r in results):
            print(
                "\n  ⚠  One or more endpoints are unreachable. Start the "
                "required servers before sending queries.\n"
                "     1) python mcp_servers/search_mcp.py\n"
                "     2) python mcp_servers/report_mcp.py\n"
                "     3) python acp_server.py"
            )
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
            reset_thread(thread_id)
            thread_id = uuid.uuid4().hex
            _current_config["configurable"]["thread_id"] = thread_id
            _current_supervisor = None
            print("--- New conversation started ---")
            continue

        logger.info("User query: %s", user_input)
        # Reset the per-turn research revision budget, but keep the
        # cached Supervisor + shared checkpointer so LangGraph sees
        # prior conversation state.
        reset_revision_counter(thread_id)
        _current_supervisor = get_or_create_supervisor(thread_id)

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
