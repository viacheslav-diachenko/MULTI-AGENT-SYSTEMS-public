"""Tests for Pydantic structured output schemas."""

import pytest
from schemas import ResearchPlan, CritiqueResult


class TestResearchPlan:
    def test_valid_plan(self):
        plan = ResearchPlan(
            goal="Compare RAG approaches",
            search_queries=["naive RAG", "sentence-window RAG"],
            sources_to_check=["knowledge_base", "web"],
            output_format="comparison table with pros/cons",
        )
        assert plan.goal == "Compare RAG approaches"
        assert len(plan.search_queries) == 2
        assert "knowledge_base" in plan.sources_to_check

    def test_plan_json_roundtrip(self):
        plan = ResearchPlan(
            goal="Analyze LLM architectures",
            search_queries=["transformer architecture"],
            sources_to_check=["web"],
            output_format="summary report",
        )
        json_str = plan.model_dump_json()
        restored = ResearchPlan.model_validate_json(json_str)
        assert restored == plan

    def test_plan_empty_queries_rejected(self):
        with pytest.raises(Exception):
            ResearchPlan(
                goal="Test",
                search_queries=[],
                sources_to_check=["web"],
                output_format="report",
            )

    def test_plan_invalid_source_rejected(self):
        """sources_to_check must only contain 'knowledge_base' or 'web'."""
        with pytest.raises(Exception):
            ResearchPlan(
                goal="Test",
                search_queries=["query"],
                sources_to_check=["database"],
                output_format="report",
            )

    def test_plan_empty_sources_rejected(self):
        with pytest.raises(Exception):
            ResearchPlan(
                goal="Test",
                search_queries=["query"],
                sources_to_check=[],
                output_format="report",
            )

    def test_plan_single_source_knowledge_base(self):
        plan = ResearchPlan(
            goal="Test",
            search_queries=["query"],
            sources_to_check=["knowledge_base"],
            output_format="report",
        )
        assert plan.sources_to_check == ["knowledge_base"]


class TestCritiqueResult:
    def test_approve_verdict(self):
        result = CritiqueResult(
            verdict="APPROVE",
            is_fresh=True,
            is_complete=True,
            is_well_structured=True,
            strengths=["Good coverage", "Recent sources"],
            gaps=[],
            revision_requests=[],
        )
        assert result.verdict == "APPROVE"
        assert result.is_fresh is True

    def test_revise_verdict(self):
        result = CritiqueResult(
            verdict="REVISE",
            is_fresh=False,
            is_complete=False,
            is_well_structured=True,
            strengths=["Well structured"],
            gaps=["Outdated benchmarks", "Missing parent-child coverage"],
            revision_requests=["Find 2025-2026 benchmarks"],
        )
        assert result.verdict == "REVISE"
        assert len(result.gaps) == 2

    def test_invalid_verdict_rejected(self):
        with pytest.raises(Exception):
            CritiqueResult(
                verdict="MAYBE",
                is_fresh=True,
                is_complete=True,
                is_well_structured=True,
                strengths=[],
                gaps=[],
                revision_requests=[],
            )

    def test_critique_json_roundtrip(self):
        result = CritiqueResult(
            verdict="APPROVE",
            is_fresh=True,
            is_complete=True,
            is_well_structured=True,
            strengths=["Complete"],
            gaps=[],
            revision_requests=[],
        )
        json_str = result.model_dump_json()
        restored = CritiqueResult.model_validate_json(json_str)
        assert restored == result

    def test_approve_with_failed_dimension_rejected(self):
        """APPROVE verdict requires all is_* flags to be True."""
        with pytest.raises(Exception, match="verdict is APPROVE"):
            CritiqueResult(
                verdict="APPROVE",
                is_fresh=False,
                is_complete=True,
                is_well_structured=True,
                strengths=["Some strength"],
                gaps=["Stale data"],
                revision_requests=[],
            )

    def test_revise_without_revision_requests_rejected(self):
        """REVISE verdict requires non-empty revision_requests."""
        with pytest.raises(Exception, match="revision_requests is empty"):
            CritiqueResult(
                verdict="REVISE",
                is_fresh=False,
                is_complete=True,
                is_well_structured=True,
                strengths=[],
                gaps=["Stale data"],
                revision_requests=[],
            )

    def test_revise_all_dimensions_failed(self):
        result = CritiqueResult(
            verdict="REVISE",
            is_fresh=False,
            is_complete=False,
            is_well_structured=False,
            strengths=[],
            gaps=["Everything outdated", "Missing topics", "Bad structure"],
            revision_requests=["Redo the entire research"],
        )
        assert result.verdict == "REVISE"
        assert not result.is_fresh
        assert not result.is_complete
        assert not result.is_well_structured
