"""Fire a deterministic batch of 5 queries through the MAS so Langfuse
gets a clean set of traces to screenshot / auto-evaluate.

All queries picked per §Step 10 of the plan: no corporate / PII content,
covers happy / edge / failure categories.

Uses the same REPL entry point (``_run_turn``) but without stdin —
the HITL interrupt on ``save_report`` is auto-rejected on EOF via the
existing code in ``handle_interrupt``. That's fine — evaluators still
score the pre-HITL `output` of the trace.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langfuse_setup import langfuse_callback, langfuse_client  # noqa: E402
from main import _current_config, _run_turn, settings  # noqa: E402


QUERIES = [
    "One-sentence answer: what is RAG?",
    "Name two retrieval strategies mentioned in the knowledge base.",
    "LangChain vs LangGraph — two-sentence summary.",
    "Write a haiku about embeddings.",
    "List three practical tips for RAG retrieval quality.",
]


def main() -> int:
    thread_id = uuid.uuid4().hex
    _current_config.update(
        {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.max_iterations,
            "callbacks": [langfuse_callback],
        }
    )
    print(f"Thread: {thread_id}")
    for i, q in enumerate(QUERIES, 1):
        print(f"\n===== Query {i}/{len(QUERIES)} =====")
        print(f"Q: {q}")
        t0 = time.time()
        try:
            _run_turn(q, thread_id)
        except Exception as e:
            print(f"  ! exception: {e}")
        print(f"  duration: {time.time() - t0:.1f}s")

    langfuse_client.flush()
    print("\nFLUSHED — all traces delivered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
