"""Regression tests for multi-turn Supervisor caching.

``get_or_create_supervisor`` must return the same agent instance for a
given ``thread_id`` across calls so LangGraph checkpoints survive REPL
turns, and ``reset_thread`` must cleanly evict both the agent and the
revision counter.

These tests patch ``_build_supervisor_instance`` so they exercise the
caching contract without touching the real LLM / MCP / ACP stack.
"""

import pytest

import supervisor


@pytest.fixture(autouse=True)
def _clean_state():
    supervisor._supervisors.clear()
    supervisor._revision_counts.clear()
    yield
    supervisor._supervisors.clear()
    supervisor._revision_counts.clear()


@pytest.fixture
def counting_builder(monkeypatch):
    calls: list[object] = []

    def _fake_build(checkpointer):
        instance = object()
        calls.append((instance, checkpointer))
        return instance

    monkeypatch.setattr(supervisor, "_build_supervisor_instance", _fake_build)
    return calls


def test_same_thread_reuses_instance(counting_builder):
    first = supervisor.get_or_create_supervisor("thread-a")
    second = supervisor.get_or_create_supervisor("thread-a")
    assert first is second
    assert len(counting_builder) == 1


def test_different_threads_get_different_instances(counting_builder):
    a = supervisor.get_or_create_supervisor("thread-a")
    b = supervisor.get_or_create_supervisor("thread-b")
    assert a is not b
    assert len(counting_builder) == 2


def test_fresh_flag_rebuilds(counting_builder):
    a = supervisor.get_or_create_supervisor("thread-a")
    b = supervisor.get_or_create_supervisor("thread-a", fresh=True)
    assert a is not b
    assert len(counting_builder) == 2


def test_reset_thread_evicts_cache_and_counter(counting_builder):
    supervisor.get_or_create_supervisor("thread-a")
    supervisor._revision_counts["thread-a"] = 2
    supervisor.reset_thread("thread-a")
    assert "thread-a" not in supervisor._supervisors
    assert "thread-a" not in supervisor._revision_counts

    # Rebuild after reset yields a new instance.
    supervisor.get_or_create_supervisor("thread-a")
    assert len(counting_builder) == 2


def test_cache_uses_shared_checkpointer(counting_builder):
    supervisor.get_or_create_supervisor("thread-a")
    supervisor.get_or_create_supervisor("thread-b")
    checkpointers = {cp for _, cp in counting_builder}
    # All cached supervisors must share the module-level checkpointer.
    assert checkpointers == {supervisor._checkpointer}


def test_reset_thread_clears_checkpointer_state(counting_builder, monkeypatch):
    """reset_thread must evict saved LangGraph checkpoints, not just the
    cached Python instance — otherwise a rebuilt Supervisor with the
    same thread_id would silently recover the old conversation."""
    deleted: list[str] = []

    def _fake_delete(thread_id: str) -> None:
        deleted.append(thread_id)

    # Use the documented delete_thread API if the installed langgraph
    # exposes it; otherwise monkey-patch one on so the fallback path is
    # only taken when really necessary.
    monkeypatch.setattr(supervisor._checkpointer, "delete_thread", _fake_delete, raising=False)

    supervisor.get_or_create_supervisor("thread-a")
    supervisor.reset_thread("thread-a")

    assert deleted == ["thread-a"]
    assert "thread-a" not in supervisor._supervisors


def test_reset_thread_fallback_clears_in_memory_storage(counting_builder, monkeypatch):
    """When delete_thread is unavailable the helper must still wipe any
    InMemorySaver-style internal dict keyed by (thread_id, ...)."""
    fake_storage: dict = {
        ("thread-a", "", "ckpt-1"): {"data": "stale"},
        ("thread-a", "", "ckpt-2"): {"data": "stale"},
        ("thread-b", "", "ckpt-1"): {"data": "keep"},
    }
    # Strip delete_thread so the fallback branch runs.
    monkeypatch.delattr(supervisor._checkpointer, "delete_thread", raising=False)
    monkeypatch.setattr(supervisor._checkpointer, "storage", fake_storage, raising=False)

    supervisor.get_or_create_supervisor("thread-a")
    supervisor.reset_thread("thread-a")

    assert ("thread-a", "", "ckpt-1") not in fake_storage
    assert ("thread-a", "", "ckpt-2") not in fake_storage
    assert ("thread-b", "", "ckpt-1") in fake_storage


def test_fresh_flag_clears_checkpointer_state(counting_builder, monkeypatch):
    """fresh=True must fully reset the thread, not only pop the cache."""
    deleted: list[str] = []
    monkeypatch.setattr(
        supervisor._checkpointer, "delete_thread",
        lambda tid: deleted.append(tid),
        raising=False,
    )

    supervisor.get_or_create_supervisor("thread-a")
    supervisor.get_or_create_supervisor("thread-a", fresh=True)

    assert deleted == ["thread-a"]
    assert len(counting_builder) == 2
