"""Tests for thread-scoped revision counter enforcement in supervisor."""

from supervisor import (
    _get_revision_count,
    _increment_revision_count,
    reset_revision_counter,
)


class TestRevisionCounter:
    def test_reset_sets_to_zero(self):
        _increment_revision_count('test-thread-1')
        _increment_revision_count('test-thread-1')
        reset_revision_counter('test-thread-1')
        assert _get_revision_count('test-thread-1') == 0

    def test_counter_starts_at_zero(self):
        assert _get_revision_count('test-fresh') == 0

    def test_increment(self):
        reset_revision_counter('test-inc')
        assert _increment_revision_count('test-inc') == 1
        assert _increment_revision_count('test-inc') == 2
        assert _get_revision_count('test-inc') == 2

    def test_thread_isolation(self):
        """Different threads have independent counters."""
        reset_revision_counter('thread-a')
        _increment_revision_count('thread-a')
        _increment_revision_count('thread-a')

        reset_revision_counter('thread-b')
        _increment_revision_count('thread-b')

        assert _get_revision_count('thread-a') == 2
        assert _get_revision_count('thread-b') == 1

    def test_reset_does_not_affect_other_threads(self):
        reset_revision_counter('thread-x')
        _increment_revision_count('thread-x')
        _increment_revision_count('thread-x')

        reset_revision_counter('thread-y')

        assert _get_revision_count('thread-x') == 2
        assert _get_revision_count('thread-y') == 0
