"""Schema invariants — same contract as hw8."""

import pytest

from schemas import CritiqueResult, ResearchPlan


class TestResearchPlan:
    def test_valid_plan(self):
        plan = ResearchPlan(
            goal="Compare RAG approaches",
            search_queries=["naive RAG", "sentence-window RAG"],
            sources_to_check=["knowledge_base", "web"],
            output_format="comparison table with pros/cons",
        )
        assert len(plan.search_queries) == 2
        assert "web" in plan.sources_to_check

    def test_empty_queries_rejected(self):
        with pytest.raises(Exception):
            ResearchPlan(
                goal="Test",
                search_queries=[],
                sources_to_check=["web"],
                output_format="report",
            )

    def test_invalid_source_rejected(self):
        with pytest.raises(Exception):
            ResearchPlan(
                goal="Test",
                search_queries=["q"],
                sources_to_check=["database"],
                output_format="report",
            )


class TestCritiqueResult:
    def test_approve(self):
        r = CritiqueResult(
            verdict="APPROVE",
            is_fresh=True, is_complete=True, is_well_structured=True,
            strengths=["ok"], gaps=[], revision_requests=[],
        )
        assert r.verdict == "APPROVE"

    def test_approve_with_failed_dimension_rejected(self):
        with pytest.raises(Exception, match="verdict is APPROVE"):
            CritiqueResult(
                verdict="APPROVE",
                is_fresh=False, is_complete=True, is_well_structured=True,
                strengths=["s"], gaps=["g"], revision_requests=[],
            )

    def test_revise_without_requests_rejected(self):
        with pytest.raises(Exception, match="revision_requests is empty"):
            CritiqueResult(
                verdict="REVISE",
                is_fresh=False, is_complete=True, is_well_structured=True,
                strengths=[], gaps=["stale"], revision_requests=[],
            )
