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
