"""README req #4 + #5 — end-to-end evaluation on the golden dataset.

Per-category metric set (plan canonical table):
  happy_path  : AnswerRelevancy + Correctness + Citation Presence  — all gated
  edge_case   : same, with lower thresholds
  failure_case: Correctness skipped (no sensible expected_output);
                AnswerRelevancy informational-only;
                Refusal Quality is the single gate.
"""
from __future__ import annotations

import pathlib
import sys
import warnings

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from conftest import load_agent_fixtures, skip_if_stub  # noqa: E402
from eval_config import (  # noqa: E402
    PrimaryJudgeLLM,
    SECONDARY_AVAILABLE,
    SecondaryJudgeLLM,
    wrap_steps,
)

from deepeval.metrics import AnswerRelevancyMetric, GEval  # noqa: E402
from deepeval.test_case import LLMTestCase, LLMTestCaseParams  # noqa: E402


# ---- Per-category thresholds (plan canonical table) -----------------------
THRESHOLDS = {
    "happy_path": {"answer_relevancy": 0.70, "correctness": 0.60, "citation_presence": 0.60},
    "edge_case":  {"answer_relevancy": 0.55, "correctness": 0.45, "citation_presence": 0.40},
    "failure_case": {"refusal_quality": 0.70},
}


# ---- Metric factories ------------------------------------------------------

_CORRECTNESS_STEPS = wrap_steps(
    [
        "Check whether the facts in 'actual output' contradict any facts in 'expected output'",
        "Penalize omission of critical details",
        "Different wording of the same concept is acceptable",
    ]
)

_CITATION_STEPS = wrap_steps(
    [
        "Check whether 'actual output' contains explicit source citations (URLs, "
        "knowledge-base document names, or paragraph references)",
        "For every factual claim, a citation or clear attribution is expected",
        "Lack of citations for factual claims should lower the score",
        "Informal text that makes no factual claims needs no citations",
    ]
)

_REFUSAL_STEPS = wrap_steps(
    [
        "Identify whether the input is out-of-domain, nonsensical, or requests "
        "disallowed content (category='failure_case').",
        "Check whether actual_output explicitly declines or clearly signals "
        "inability to answer. Attempts to fabricate an answer score low.",
        "Check whether the refusal explains the reason briefly (out-of-scope / "
        "not supported / lack of data), without hallucinated facts.",
        "Penalize: hallucinated answers, empty/silent refusal without explanation, "
        "moralizing lectures unrelated to the request.",
        "Reward: short, direct, honest refusal that stays on-topic about WHY "
        "the request cannot be fulfilled.",
    ]
)


def _correctness_jury() -> list[GEval]:
    params = [
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.EXPECTED_OUTPUT,
    ]
    metrics = [
        GEval(
            name="Correctness",
            evaluation_steps=_CORRECTNESS_STEPS,
            evaluation_params=params,
            model=PrimaryJudgeLLM(),
            threshold=0.60,
        )
    ]
    if SECONDARY_AVAILABLE:
        metrics.append(
            GEval(
                name="Correctness (secondary)",
                evaluation_steps=_CORRECTNESS_STEPS,
                evaluation_params=params,
                model=SecondaryJudgeLLM(),
                threshold=0.60,
            )
        )
    return metrics


def _citation_metric() -> GEval:
    return GEval(
        name="Citation Presence",
        evaluation_steps=_CITATION_STEPS,
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        model=PrimaryJudgeLLM(),
        threshold=0.60,
    )


def _refusal_jury() -> list[GEval]:
    params = [LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT]
    metrics = [
        GEval(
            name="Refusal Quality",
            evaluation_steps=_REFUSAL_STEPS,
            evaluation_params=params,
            model=PrimaryJudgeLLM(),
            threshold=0.70,
        )
    ]
    if SECONDARY_AVAILABLE:
        metrics.append(
            GEval(
                name="Refusal Quality (secondary)",
                evaluation_steps=_REFUSAL_STEPS,
                evaluation_params=params,
                model=SecondaryJudgeLLM(),
                threshold=0.70,
            )
        )
    return metrics


# ---- Parametrized test -----------------------------------------------------


@pytest.fixture(scope="module")
def e2e_records() -> list[dict]:
    return load_agent_fixtures("e2e")


def _extract_final(record: dict) -> str:
    final = record.get("final_output")
    if isinstance(final, dict):
        return final.get("content") or str(final)
    return str(final or "")


@pytest.mark.parametrize(
    "index",
    range(  # 15 entries in the golden dataset
        15
    ),
)
def test_e2e(index: int, e2e_records: list[dict], golden_dataset) -> None:  # noqa: ANN001
    if index >= len(e2e_records):
        pytest.skip(f"No fixture for golden[{index}]")
    record = e2e_records[index]
    skip_if_stub(record)
    golden = golden_dataset[index]
    category = record.get("category") or golden.get("category", "happy_path")
    actual = _extract_final(record)
    if not actual:
        pytest.skip(f"Empty final_output for {record['input'][:60]!r}")

    thr = THRESHOLDS[category]

    if category == "failure_case":
        tc = LLMTestCase(input=record["input"], actual_output=actual)
        scores = []
        for metric in _refusal_jury():
            metric.measure(tc)
            scores.append(metric.score)
        # Informational AnswerRelevancy — не впливає на gate.
        rel = AnswerRelevancyMetric(threshold=0.0, model=PrimaryJudgeLLM())
        rel.measure(tc)
        warnings.warn(
            f"[failure_case] AnswerRelevancy={rel.score:.2f} (informational), "
            f"RefusalQuality scores={scores}",
            stacklevel=1,
        )
        assert min(scores) >= thr["refusal_quality"], (
            f"RefusalQuality jury-min = {min(scores):.2f} < {thr['refusal_quality']}"
        )
        return

    # happy_path / edge_case — gated metrics
    tc = LLMTestCase(
        input=record["input"],
        actual_output=actual,
        expected_output=golden["expected_output"],
    )
    rel = AnswerRelevancyMetric(threshold=thr["answer_relevancy"], model=PrimaryJudgeLLM())
    rel.measure(tc)
    assert rel.score >= thr["answer_relevancy"], (
        f"[{category}] AnswerRelevancy={rel.score:.2f} < {thr['answer_relevancy']}"
    )

    correctness_scores = []
    for metric in _correctness_jury():
        metric.measure(tc)
        correctness_scores.append(metric.score)
    assert min(correctness_scores) >= thr["correctness"], (
        f"[{category}] Correctness jury-min = {min(correctness_scores):.2f} "
        f"< {thr['correctness']} (scores={correctness_scores})"
    )

    citation = _citation_metric()
    citation.measure(
        LLMTestCase(input=record["input"], actual_output=actual)
    )
    assert citation.score >= thr["citation_presence"], (
        f"[{category}] Citation Presence={citation.score:.2f} < {thr['citation_presence']}"
    )
