"""Tests for revision counter enforcement in supervisor."""

from supervisor import reset_revision_counter, _revision_count
import supervisor


class TestRevisionCounter:
    def test_reset_sets_to_zero(self):
        supervisor._revision_count = 5
        reset_revision_counter()
        assert supervisor._revision_count == 0

    def test_counter_starts_at_zero(self):
        reset_revision_counter()
        assert supervisor._revision_count == 0
