"""Live canary — не в default suite. Запускати вручну перед релізом:

    pytest tests/smoke/ -m live

Мінімальний прохід 1 запиту через supervisor. Ловить інтеграційні поломки
(нова версія fastmcp, зміна endpoint-у vLLM, зламаний ACP), які fixture-only
тести не побачать до наступного record_fixtures.
"""
from __future__ import annotations

import json
import pathlib
import sys
import uuid

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))


@pytest.mark.live
def test_supervisor_end_to_end_smoke() -> None:
    pytest.importorskip("config")
    import asyncio

    import supervisor  # type: ignore
    try:
        import schemas  # type: ignore
    except ImportError:
        schemas = None

    tid = uuid.uuid4().hex
    app = supervisor.get_or_create_supervisor(tid, fresh=True)

    async def _run() -> dict:
        return await app.ainvoke(
            {"messages": [{"role": "user", "content": "What is LangGraph?"}]},
            config={"configurable": {"thread_id": tid}},
        )

    try:
        state = asyncio.run(_run())
    finally:
        reset = getattr(supervisor, "reset_thread", None)
        if callable(reset):
            reset(tid)

    messages = state.get("messages", [])
    assert messages, "Supervisor returned no messages"
    last = messages[-1]
    content = getattr(last, "content", None) or (last.get("content") if isinstance(last, dict) else "")
    assert content, "Final message has empty content"

    # Спробуємо витягти ResearchPlan з проміжних кроків (hw8/schemas.py)
    if schemas is not None and hasattr(schemas, "ResearchPlan"):
        for msg in messages:
            txt = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else "")
            if not isinstance(txt, str) or "search_queries" not in txt:
                continue
            try:
                schemas.ResearchPlan.model_validate_json(txt)
                return
            except Exception:
                continue
