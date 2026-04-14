"""README req #2 — Researcher component test.

Primary metric: custom GEval Groundedness (README lines 84–101) — strict,
gates every claim on retrieval context. Paired with FaithfulnessMetric
(built-in, looser) for didactic comparison per Lesson 10 Block 4.2.

retrieval_context comes from hw8's HybridRetriever.search(). If the
retriever is unavailable at runtime (no index built, for example), the test
is skipped with a clear reason — README requires *a* Researcher metric but
does not pin it to RAG.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from conftest import load_agent_fixtures, skip_if_stub  # noqa: E402
from eval_config import (  # noqa: E402
    PrimaryJudgeLLM,
    SECONDARY_AVAILABLE,
    SecondaryJudgeLLM,
    wrap_steps,
)

from deepeval.metrics import FaithfulnessMetric, GEval  # noqa: E402
from deepeval.test_case import LLMTestCase, LLMTestCaseParams  # noqa: E402


_GROUNDEDNESS_STEPS = wrap_steps(
    [
        "Extract every factual claim from 'actual output'",
        "For each claim, check if it can be directly supported by 'retrieval context'",
        "Claims not present in retrieval context count as ungrounded, even if true",
        "Score = number of grounded claims / total claims",
    ]
)


def _retrieve_context(query: str) -> list[str]:
    """Get top-K chunks from hw8's hybrid retriever."""
    try:
        from retriever import get_retriever  # type: ignore
    except ImportError:
        return []
    try:
        retriever = get_retriever()
    except Exception:
        return []
    docs = retriever.search(query, rerank_top_n=5) if hasattr(retriever, "search") else retriever.get_relevant_documents(query)
    return [getattr(d, "page_content", str(d)) for d in docs]


def _build_groundedness_jury() -> list[GEval]:
    metrics = [
        GEval(
            name="Groundedness",
            evaluation_steps=_GROUNDEDNESS_STEPS,
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.RETRIEVAL_CONTEXT,
            ],
            model=PrimaryJudgeLLM(),
            threshold=0.65,
        )
    ]
    if SECONDARY_AVAILABLE:
        metrics.append(
            GEval(
                name="Groundedness (secondary)",
                evaluation_steps=_GROUNDEDNESS_STEPS,
                evaluation_params=[
                    LLMTestCaseParams.ACTUAL_OUTPUT,
                    LLMTestCaseParams.RETRIEVAL_CONTEXT,
                ],
                model=SecondaryJudgeLLM(),
                threshold=0.65,
            )
        )
    return metrics


@pytest.mark.parametrize("record", load_agent_fixtures("researcher"))
def test_researcher_groundedness(record: dict) -> None:
    skip_if_stub(record)
    outputs = record["outputs"]
    if not outputs:
        pytest.skip(f"No researcher output captured for input: {record['input'][:60]!r}")
    actual = outputs[-1]
    context = _retrieve_context(record["input"])
    if not context:
        pytest.skip(
            "Empty retrieval_context — either retriever unavailable (hw8-mode) "
            "or KB has no match. Groundedness requires context."
        )
    tc = LLMTestCase(
        input=record["input"],
        actual_output=actual,
        retrieval_context=context,
    )
    scores = []
    for metric in _build_groundedness_jury():
        metric.measure(tc)
        scores.append(metric.score)
    strict = min(scores)
    assert strict >= 0.65, (
        f"Groundedness jury-min = {strict:.2f} < 0.65 "
        f"(per-judge: {scores}) for {record['input'][:80]!r}"
    )


@pytest.mark.parametrize("record", load_agent_fixtures("researcher"))
def test_researcher_faithfulness_reference(record: dict) -> None:
    """Didactic companion per Lesson Block 4.2 — informational only, не gate.
    Порівнюємо з Groundedness, щоб у CHANGELOG зафіксувати розрив."""
    skip_if_stub(record)
    outputs = record["outputs"]
    if not outputs:
        pytest.skip("No researcher output.")
    actual = outputs[-1]
    context = _retrieve_context(record["input"])
    if not context:
        pytest.skip("Empty retrieval_context.")
    metric = FaithfulnessMetric(threshold=0.70, model=PrimaryJudgeLLM())
    tc = LLMTestCase(
        input=record["input"], actual_output=actual, retrieval_context=context
    )
    metric.measure(tc)
    # Informational — do not fail on FaithfulnessMetric; pytest warning preserves signal.
    if metric.score < 0.70:
        import warnings

        warnings.warn(
            f"Faithfulness={metric.score:.2f} below 0.70 for {record['input'][:60]!r} — "
            "compare with Groundedness score.",
            stacklevel=1,
        )
