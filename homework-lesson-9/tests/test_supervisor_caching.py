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
