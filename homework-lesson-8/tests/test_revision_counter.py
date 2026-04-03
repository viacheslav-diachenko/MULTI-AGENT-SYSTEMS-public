"""Tests for thread-scoped revision counter enforcement in supervisor."""

import supervisor
from supervisor import (
    reset_revision_counter,
    set_active_thread,
    _get_revision_count,
    _increment_revision_count,
)


class TestRevisionCounter:
    def test_reset_sets_to_zero(self):
        set_active_thread("test-thread-1")
        supervisor._revision_counts["test-thread-1"] = 5
        reset_revision_counter("test-thread-1")
        assert _get_revision_count() == 0

    def test_counter_starts_at_zero(self):
        set_active_thread("test-fresh")
        assert _get_revision_count() == 0

    def test_increment(self):
        set_active_thread("test-inc")
        reset_revision_counter("test-inc")
        assert _increment_revision_count() == 1
        assert _increment_revision_count() == 2
        assert _get_revision_count() == 2

    def test_thread_isolation(self):
        """Different threads have independent counters."""
        set_active_thread("thread-a")
        reset_revision_counter("thread-a")
        _increment_revision_count()
        _increment_revision_count()

        set_active_thread("thread-b")
        reset_revision_counter("thread-b")
        _increment_revision_count()

        # thread-a should still be at 2
        set_active_thread("thread-a")
        assert _get_revision_count() == 2

        # thread-b should be at 1
        set_active_thread("thread-b")
        assert _get_revision_count() == 1

    def test_reset_does_not_affect_other_threads(self):
        set_active_thread("thread-x")
        reset_revision_counter("thread-x")
        _increment_revision_count()
        _increment_revision_count()

        set_active_thread("thread-y")
        reset_revision_counter("thread-y")

        # thread-x still at 2
        set_active_thread("thread-x")
        assert _get_revision_count() == 2
