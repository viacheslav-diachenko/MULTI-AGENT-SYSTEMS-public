"""README req #2 — Planner component test.

Structural pre-check: parse actual_output as ResearchPlan (from hw8/schemas.py).
LLM-judge layer: GEval Plan Quality (README lines 54–65), primary judge only
(cheap metric, secondary reserved for gating-level metrics).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from conftest import load_agent_fixtures, skip_if_stub  # noqa: E402
from eval_config import PrimaryJudgeLLM, wrap_steps  # noqa: E402

from deepeval.metrics import GEval  # noqa: E402
from deepeval.test_case import LLMTestCase, LLMTestCaseParams  # noqa: E402

from schemas import ResearchPlan  # type: ignore  # noqa: E402


_PLAN_QUALITY_STEPS = wrap_steps(
    [
        "Check that the plan contains specific search queries (not vague)",
        "Check that sources_to_check includes relevant sources for the topic",
        "Check that the output_format matches what the user asked for",
    ]
)


def _plan_quality() -> GEval:
    return GEval(
        name="Plan Quality",
        evaluation_steps=_PLAN_QUALITY_STEPS,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=PrimaryJudgeLLM(),
        threshold=0.70,
    )


@pytest.mark.parametrize("record", load_agent_fixtures("planner"))
def test_plan_structure(record: dict) -> None:
    skip_if_stub(record)
    outputs = record["outputs"]
    if not outputs:
        pytest.skip(f"No planner output captured for input: {record['input'][:60]!r}")
    last = outputs[-1]
    try:
        plan = ResearchPlan.model_validate_json(last)
    except Exception as exc:
        raise AssertionError(
            f"Planner output is not valid ResearchPlan JSON: {last[:300]!r}"
        ) from exc
    assert plan.search_queries, "ResearchPlan.search_queries must be non-empty"
    assert plan.sources_to_check, "ResearchPlan.sources_to_check must be non-empty"


@pytest.mark.parametrize("record", load_agent_fixtures("planner"))
def test_plan_quality(record: dict) -> None:
    skip_if_stub(record)
    outputs = record["outputs"]
    if not outputs:
        pytest.skip(f"No planner output captured for input: {record['input'][:60]!r}")
    last = outputs[-1]
    test_case = LLMTestCase(input=record["input"], actual_output=last)
    metric = _plan_quality()
    metric.measure(test_case)
    assert metric.score >= 0.70, (
        f"Plan Quality = {metric.score:.2f} < 0.70 "
        f"(reason: {metric.reason})"
    )
