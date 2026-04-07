"""Pydantic models for structured agent outputs.

ResearchPlan — returned by Planner Agent.
CritiqueResult — returned by Critic Agent.

Verbatim from hw8: same contracts so the Supervisor logic does not change.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SourceType = Literal["knowledge_base", "web"]


class ResearchPlan(BaseModel):
    """Structured research plan produced by the Planner Agent."""

    goal: str = Field(description="What we are trying to answer")
    search_queries: list[str] = Field(
        description="Specific queries to execute (at least one)",
    )
    sources_to_check: list[SourceType] = Field(
        description="Where to search: 'knowledge_base', 'web', or both",
    )
    output_format: str = Field(
        description="What the final report should look like",
    )

    @field_validator("search_queries")
    @classmethod
    def at_least_one_query(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("search_queries must contain at least one query")
        return v

    @field_validator("sources_to_check")
    @classmethod
    def at_least_one_source(cls, v: list[SourceType]) -> list[SourceType]:
        if not v:
            raise ValueError("sources_to_check must contain at least one source")
        return v


class CritiqueResult(BaseModel):
    """Structured critique produced by the Critic Agent."""

    verdict: Literal["APPROVE", "REVISE"] = Field(
        description="APPROVE to accept findings, REVISE to send back for improvement",
    )
    is_fresh: bool = Field(description="Is the data up-to-date?")
    is_complete: bool = Field(description="Does the research cover the request?")
    is_well_structured: bool = Field(description="Are findings logically organised?")
    strengths: list[str] = Field(description="What is good about the research")
    gaps: list[str] = Field(description="What is missing, outdated, or poorly structured")
    revision_requests: list[str] = Field(description="Specific things to fix if REVISE")

    @model_validator(mode="after")
    def check_verdict_consistency(self) -> "CritiqueResult":
        if self.verdict == "APPROVE" and not (
            self.is_fresh and self.is_complete and self.is_well_structured
        ):
            raise ValueError(
                "verdict is APPROVE but not all dimensions are True "
                f"(fresh={self.is_fresh}, complete={self.is_complete}, "
                f"structured={self.is_well_structured})"
            )
        if self.verdict == "REVISE" and not self.revision_requests:
            raise ValueError(
                "verdict is REVISE but revision_requests is empty — "
                "Critic must specify what to fix"
            )
        return self
