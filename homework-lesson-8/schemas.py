"""Pydantic models for structured agent outputs.

ResearchPlan — returned by Planner Agent.
CritiqueResult — returned by Critic Agent.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ResearchPlan(BaseModel):
    """Structured research plan produced by the Planner Agent."""

    goal: str = Field(description="What we are trying to answer")
    search_queries: list[str] = Field(
        description="Specific queries to execute (at least one)",
    )
    sources_to_check: list[str] = Field(
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


class CritiqueResult(BaseModel):
    """Structured critique produced by the Critic Agent."""

    verdict: Literal["APPROVE", "REVISE"] = Field(
        description="APPROVE to accept findings, REVISE to send back for improvement",
    )
    is_fresh: bool = Field(
        description="Is the data up-to-date and based on recent sources?",
    )
    is_complete: bool = Field(
        description="Does the research fully cover the user's original request?",
    )
    is_well_structured: bool = Field(
        description="Are findings logically organized and ready for a report?",
    )
    strengths: list[str] = Field(
        description="What is good about the research",
    )
    gaps: list[str] = Field(
        description="What is missing, outdated, or poorly structured",
    )
    revision_requests: list[str] = Field(
        description="Specific things to fix if verdict is REVISE",
    )
