"""Record actual_output + tool_calls for every agent role across the golden
dataset. Writes fixtures/hw8/*_outputs.json and a freshness manifest.

Fail-loud: any error raises instead of silently appending {"error": ...} —
dirty fixtures are worse than no fixtures.

Dirty-tree guard: refuses to run if hw10 has uncommitted changes in runtime
paths (config / supervisor / agents / tools / etc.), unless --allow-dirty.

Usage:
    python scripts/record_fixtures.py                 # strict (default)
    python scripts/record_fixtures.py --allow-dirty   # ad-hoc debug
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import os
import pathlib
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
BASE_DIR = PROJECT_ROOT  # hw8 source files live under hw10 directly
sys.path.insert(0, str(PROJECT_ROOT))

FIXTURES_DIR = PROJECT_ROOT / "fixtures" / "hw8"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

RUNTIME_PATHS = [
    "homework-lesson-10/config.py",
    "homework-lesson-10/supervisor.py",
    "homework-lesson-10/retriever.py",
    "homework-lesson-10/tools.py",
    "homework-lesson-10/main.py",
    "homework-lesson-10/schemas.py",
    "homework-lesson-10/tool_parser.py",
    "homework-lesson-10/agents",
]


def _git(args: list[str]) -> str:
    r = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({r.returncode}): {r.stderr.strip()}"
        )
    return r.stdout.strip()


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _prompts_hash() -> str:
    """Hash the *source code* of prompt-builder functions, not their runtime
    output. Supervisor/Critic prompts embed ``datetime.now()`` at call-time,
    so hashing the returned string changes every microsecond — that broke the
    freshness manifest (every test session saw false prompts_hash drift and
    skipped the suite). Hashing the source tracks real prompt edits and
    remains stable between recording and verification."""
    import config  # type: ignore

    chunks: list[bytes] = []
    for name in (
        "get_supervisor_prompt",
        "get_planner_prompt",
        "get_researcher_prompt",
        "get_critic_prompt",
    ):
        fn = getattr(config, name, None)
        if callable(fn):
            chunks.append(inspect.getsource(fn).encode("utf-8"))
    if not chunks:
        chunks.append((BASE_DIR / "config.py").read_bytes())
    return _hash_bytes(b"\n---\n".join(chunks))


def _corpus_hash() -> str | None:
    """Hash of FAISS index + doc manifest. Returns None if base has no RAG corpus."""
    index_dir = BASE_DIR / "index"
    if not index_dir.is_dir():
        return None
    h = hashlib.sha256()
    for p in sorted(index_dir.rglob("*")):
        if p.is_file():
            h.update(p.name.encode("utf-8"))
            h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()


def _golden_hash() -> str:
    return _hash_bytes((PROJECT_ROOT / "tests" / "golden_dataset.json").read_bytes())


def _model_endpoint_hash() -> str:
    from config import Settings  # type: ignore

    s = Settings()
    sig = f"{getattr(s, 'api_base', '')}|{getattr(s, 'model_name', '')}|{getattr(s, 'temperature', '')}"
    return _hash_bytes(sig.encode("utf-8"))


def _runtime_dirty() -> tuple[bool, str]:
    out = _git(["status", "--porcelain", "--", *RUNTIME_PATHS])
    return (bool(out.strip()), out)


def _safe_dump(record: Any) -> Any:
    """Convert LangChain messages / BaseModel instances to plain dicts."""
    try:
        from pydantic import BaseModel

        if isinstance(record, BaseModel):
            return record.model_dump()
    except ImportError:
        pass
    if hasattr(record, "content") and hasattr(record, "type"):
        return {"type": getattr(record, "type", ""), "content": record.content}
    if isinstance(record, list):
        return [_safe_dump(x) for x in record]
    if isinstance(record, dict):
        return {k: _safe_dump(v) for k, v in record.items()}
    return record


# Supervisor-level tools that wrap a sub-agent. Tool names must match the
# @tool functions registered in supervisor.build_supervisor() — supervisor.py
# passes them as `plan/research/critique` (not `delegate_to_*`). When one of
# these tools starts, its run_id is tagged with the sub-agent name and every
# nested tool_call inherits the tag via parent_of walk.
_DELEGATION_TO_AGENT = {
    "plan": "planner",
    "research": "researcher",
    "critique": "critic",
}


async def _record_single(golden_entry: dict) -> dict:
    """Invoke supervisor once, capture per-agent outputs + agent-tagged tool calls.

    Agent attribution strategy: the LangChain callback tracks parent_run_id for
    every chain/tool start. When a tool call fires, we walk the parent chain
    upward until we hit a run_id previously tagged as a delegation tool — that
    tells us which sub-agent owns the call. Supervisor-level tools (``save_report``,
    delegations themselves) get ``agent="supervisor"``.
    """
    import supervisor  # type: ignore

    thread_id = uuid.uuid4().hex
    tool_calls: list[dict] = []
    agent_outputs: dict[str, list[str]] = {
        "planner": [],
        "researcher": [],
        "critic": [],
    }

    # run_id → parent_run_id (edges in the run tree)
    parent_of: dict[str, str] = {}
    # run_id → sub-agent name, populated when a delegation tool starts
    agent_tag_of: dict[str, str] = {}

    from langchain_core.callbacks.base import AsyncCallbackHandler

    def _resolve_agent(run_id: str) -> str:
        """Walk up parent_of until we meet a tagged delegation, else 'supervisor'."""
        seen = set()
        cur = run_id
        while cur and cur not in seen:
            seen.add(cur)
            if cur in agent_tag_of:
                return agent_tag_of[cur]
            cur = parent_of.get(cur, "")
        return "supervisor"

    class _Capture(AsyncCallbackHandler):
        async def on_chain_start(self, serialized, inputs, **kw):
            rid = str(kw.get("run_id", ""))
            prid = str(kw.get("parent_run_id", "") or "")
            if rid:
                parent_of[rid] = prid

        async def on_tool_start(self, serialized, input_str, **kw):
            rid = str(kw.get("run_id", ""))
            prid = str(kw.get("parent_run_id", "") or "")
            name = serialized.get("name", "<unknown>")
            if rid:
                parent_of[rid] = prid
                if name in _DELEGATION_TO_AGENT:
                    agent_tag_of[rid] = _DELEGATION_TO_AGENT[name]
            agent = _DELEGATION_TO_AGENT.get(name) or _resolve_agent(prid)
            tool_calls.append(
                {
                    "name": name,
                    "input": input_str,
                    "run_id": rid,
                    "parent_run_id": prid,
                    "agent": agent,
                }
            )

        async def on_tool_end(self, output, **kw):
            run_id = str(kw.get("run_id", ""))
            for tc in tool_calls:
                if tc["run_id"] == run_id and "output" not in tc:
                    tc["output"] = str(output)[:4000]
                    break

    supervisor_app = supervisor.get_or_create_supervisor(thread_id, fresh=True)
    config = {"configurable": {"thread_id": thread_id}, "callbacks": [_Capture()]}
    final_state = await supervisor_app.ainvoke(
        {"messages": [{"role": "user", "content": golden_entry["input"]}]},
        config=config,
    )

    # Per-agent outputs: use the delegation tool's output as the authoritative
    # answer for that agent (it's the sub-agent's structured response).
    for tc in tool_calls:
        if tc["name"] in _DELEGATION_TO_AGENT and "output" in tc:
            agent_outputs[_DELEGATION_TO_AGENT[tc["name"]]].append(tc["output"])

    return {
        "input": golden_entry["input"],
        "category": golden_entry["category"],
        "thread_id": thread_id,
        "final_output": _safe_dump(final_state.get("messages", [])[-1]) if final_state.get("messages") else None,
        "tool_calls": tool_calls,
        "agent_outputs": agent_outputs,
    }


def _reset_supervisor(thread_id: str) -> None:
    import supervisor  # type: ignore

    reset = getattr(supervisor, "reset_thread", None)
    if callable(reset):
        try:
            reset(thread_id)
        except Exception as exc:
            raise RuntimeError(f"reset_thread failed for {thread_id}: {exc}") from exc


async def _main_async(golden: list[dict]) -> list[dict]:
    records = []
    for i, entry in enumerate(golden, 1):
        print(f"  [{i}/{len(golden)}] {entry['category']:<13} {entry['input'][:60]!r}")
        rec = await _record_single(entry)
        records.append(rec)
        _reset_supervisor(rec["thread_id"])
    return records


def _write_per_agent(records: list[dict]) -> None:
    """Split records into {planner,researcher,critic,e2e}_outputs.json.

    Per-agent tool_calls уже протеговані полем ``agent`` через run_tree
    attribution в _record_single; тут фільтруємо за цим тегом — не за
    підстрокою в імені tool-а (що плутало b overlap web_search між Planner
    і Researcher).
    """
    for role in ("planner", "researcher", "critic"):
        payload = [
            {
                "input": r["input"],
                "category": r["category"],
                "thread_id": r["thread_id"],
                "outputs": r["agent_outputs"].get(role, []),
                "tool_calls": [tc for tc in r["tool_calls"] if tc.get("agent") == role],
            }
            for r in records
        ]
        (FIXTURES_DIR / f"{role}_outputs.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False)
        )
    # e2e = full record as-is (each tool_call already carries its agent tag)
    (FIXTURES_DIR / "e2e_outputs.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False)
    )


def _write_manifest(allow_dirty: bool, was_dirty: bool) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hw_base": "hw8",
        "base_commit": _git(["rev-parse", "HEAD"]),
        "base_dirty": was_dirty if allow_dirty else False,
        "model_name": __import__("config").Settings().model_name,
        "model_endpoint_hash": _model_endpoint_hash(),
        "prompts_hash": _prompts_hash(),
        "corpus_hash": _corpus_hash(),
        "golden_dataset_hash": _golden_hash(),
    }
    (FIXTURES_DIR / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()

    dirty, porcelain = _runtime_dirty()
    if dirty and not args.allow_dirty:
        raise SystemExit(
            f"Runtime paths dirty:\n{porcelain}\n"
            "Commit/stash or pass --allow-dirty (fixtures will be marked dirty)."
        )

    golden = json.loads(
        (PROJECT_ROOT / "tests" / "golden_dataset.json").read_text()
    )
    print(f"Recording fixtures for hw10 ({len(golden)} examples)…")
    records = asyncio.run(_main_async(golden))
    _write_per_agent(records)
    _write_manifest(allow_dirty=args.allow_dirty, was_dirty=dirty)
    print(f"Wrote {len(records)} records → {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
