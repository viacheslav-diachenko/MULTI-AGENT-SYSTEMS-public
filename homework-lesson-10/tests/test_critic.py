"""README req #2 — Critic component tests.

Two layers per Lesson 10 Block 1.3:
  - Deterministic (pydantic): cheap structural contract on CritiqueResult
    (verdict ↔ revision_requests consistency).
  - LLM-judge: GEval Critique Quality (README lines 70–81); min(primary, secondary)
    if secondary judge available.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

# Ensure hw10 root is on path (for conftest and eval_config imports at runtime).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from conftest import load_agent_fixtures, skip_if_stub  # noqa: E402
from eval_config import (  # noqa: E402
    PrimaryJudgeLLM,
    SECONDARY_AVAILABLE,
    SecondaryJudgeLLM,
    wrap_steps,
)

from deepeval.metrics import GEval  # noqa: E402
from deepeval.test_case import LLMTestCase, LLMTestCaseParams  # noqa: E402


# ---- Deterministic layer ---------------------------------------------------

from schemas import CritiqueResult  # type: ignore  # noqa: E402


def _load_critic_records() -> list[dict]:
    return load_agent_fixtures("critic")


@pytest.mark.parametrize("record", _load_critic_records())
def test_critic_verdict_contract(record: dict) -> None:
    """verdict=APPROVE ⇒ no revision_requests; REVISE ⇒ ≥1 revision_request."""
    skip_if_stub(record)
    outputs = record["outputs"]
    if not outputs:
        pytest.skip(f"No critic output captured for input: {record['input'][:60]!r}")
    # Критик може викликатися кілька разів (revision rounds); беремо останню.
    last = outputs[-1]
    try:
        parsed = CritiqueResult.model_validate_json(last)
    except Exception:
        # Deterministic layer must not swallow bad JSON (hw8 CHANGELOG lesson).
        raise AssertionError(
            f"Critic output is not valid CritiqueResult JSON: {last[:300]!r}"
        )

    if parsed.verdict == "APPROVE":
        assert not parsed.revision_requests or parsed.gaps == [], (
            "APPROVE verdict must have empty revision_requests or empty gaps, "
            f"got revision_requests={parsed.revision_requests}, gaps={parsed.gaps}"
        )
    elif parsed.verdict == "REVISE":
        assert len(parsed.revision_requests) >= 1, (
            "REVISE verdict must carry at least one revision_request"
        )


# ---- LLM-judge layer -------------------------------------------------------

_CRITIQUE_QUALITY_STEPS = wrap_steps(
    [
        "Check that the critique identifies specific issues, not vague complaints",
        "Check that revision_requests are actionable (a researcher can act on them)",
        "If verdict is APPROVE, gaps list should be empty or contain only minor items",
        "If verdict is REVISE, there must be at least one revision_request",
    ]
)


def _build_jury() -> list[GEval]:
    metrics = [
        GEval(
            name="Critique Quality",
            evaluation_steps=_CRITIQUE_QUALITY_STEPS,
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            model=PrimaryJudgeLLM(),
            threshold=0.70,
        )
    ]
    if SECONDARY_AVAILABLE:
        metrics.append(
            GEval(
                name="Critique Quality (secondary)",
                evaluation_steps=_CRITIQUE_QUALITY_STEPS,
                evaluation_params=[
                    LLMTestCaseParams.INPUT,
                    LLMTestCaseParams.ACTUAL_OUTPUT,
                ],
                model=SecondaryJudgeLLM(),
                threshold=0.70,
            )
        )
    return metrics


@pytest.mark.parametrize("record", _load_critic_records())
def test_critique_quality_jury(record: dict) -> None:
    skip_if_stub(record)
    outputs = record["outputs"]
    if not outputs:
        pytest.skip(f"No critic output captured for input: {record['input'][:60]!r}")
    last = outputs[-1]
    test_case = LLMTestCase(input=record["input"], actual_output=last)
    scores = []
    for metric in _build_jury():
        metric.measure(test_case)
        scores.append(metric.score)
    strict = min(scores)
    assert strict >= 0.70, (
        f"Critique Quality jury-min = {strict:.2f} < 0.70 "
        f"(per-judge: {scores}) for input: {record['input'][:80]!r}"
    )
