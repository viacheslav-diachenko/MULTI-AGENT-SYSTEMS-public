"""Enhancement — Ragas LLMContextRecall for retriever diagnostics (Lesson 10 Block 2.2+6).

Not README-required; not in default suite (excluded via pytest.ini).
Run explicitly:

    pytest tests/enhancements/test_retriever.py -m enhancement
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

pytestmark = pytest.mark.enhancement

try:
    from retriever import get_retriever  # type: ignore
except ImportError:
    pytest.skip("Retriever module unavailable (hw8-mode?)", allow_module_level=True)

from eval_config import PrimaryJudgeLLM  # noqa: E402

ragas_metrics = pytest.importorskip("ragas.metrics", reason="ragas not installed")
ragas_schema = pytest.importorskip("ragas.dataset_schema")


@pytest.fixture(scope="module")
def retriever():
    return get_retriever()


def _has_kb_expectation(entry: dict) -> bool:
    return "knowledge_base" in (entry.get("expected_sources") or [])


@pytest.mark.parametrize("entry_index", list(range(15)))
def test_context_recall(entry_index: int, golden_dataset, retriever) -> None:  # noqa: ANN001
    if entry_index >= len(golden_dataset):
        pytest.skip()
    entry = golden_dataset[entry_index]
    if not _has_kb_expectation(entry):
        pytest.skip("Entry does not expect KB retrieval.")

    docs = (
        retriever.search(entry["input"], rerank_top_n=5)
        if hasattr(retriever, "search")
        else retriever.get_relevant_documents(entry["input"])
    )
    contexts = [getattr(d, "page_content", str(d)) for d in docs]
    if not contexts:
        pytest.fail(f"Retriever returned 0 docs for KB-expected input: {entry['input'][:80]!r}")

    from ragas import evaluate as ragas_evaluate
    from ragas.llms import LangchainLLMWrapper

    sample = ragas_schema.SingleTurnSample(
        user_input=entry["input"],
        retrieved_contexts=contexts,
        reference=entry["expected_output"],
    )
    llm = LangchainLLMWrapper(PrimaryJudgeLLM().load_model())
    result = ragas_evaluate(
        dataset=ragas_schema.EvaluationDataset(samples=[sample])
        if hasattr(ragas_schema, "EvaluationDataset")
        else [sample],
        metrics=[ragas_metrics.LLMContextRecall(llm=llm)],
        llm=llm,
    )
    score = float(result["llm_context_recall"][0]) if "llm_context_recall" in result else float(result.scores[0])

    # Informational — не блокуємо, лише warning.
    if score < 0.5:
        import warnings

        warnings.warn(
            f"LLMContextRecall={score:.2f} below 0.5 for {entry['input'][:60]!r} — "
            "retriever may be missing critical documents.",
            stacklevel=1,
        )
