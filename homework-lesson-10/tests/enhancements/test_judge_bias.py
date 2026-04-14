"""Enhancement — Position Bias Detector (Lesson 10 Exercise 3).

Swap-technique: one-shot judge sanity check. Not regression, not gated.
Writes disagreement report to fixtures/_judge_bias_report.json.

Run:
    pytest tests/enhancements/test_judge_bias.py -m enhancement
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

pytestmark = pytest.mark.enhancement

from eval_config import PrimaryJudgeLLM, SECONDARY_AVAILABLE, SecondaryJudgeLLM  # noqa: E402

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REPORT_PATH = PROJECT_ROOT / "fixtures" / "_judge_bias_report.json"

JUDGE_PROMPT = """Compare two responses to the question. Which is better?

Question: {question}
Response A: {a}
Response B: {b}

Reply with ONLY one of: A, B, tie. Do not consider response length.
"""

# 5 synthetic pairs з контрольованою різницею якості.
PAIRS = [
    (
        "What is prompt engineering?",
        "Prompt engineering is the discipline of crafting inputs to LLMs so that the output is controllable, reliable and aligned with the task. It spans techniques like zero-shot, few-shot, chain-of-thought, and schema-constrained generation.",
        "It's when you write text for AI.",
    ),
    (
        "Explain the purpose of a vector database.",
        "A vector database stores high-dimensional embeddings and supports fast approximate nearest-neighbour search, enabling semantic retrieval over text, images, or other content.",
        "It stores numbers.",
    ),
    (
        "What does temperature=0.0 do in an LLM call?",
        "Temperature=0.0 makes the sampling greedy, so the model picks the token with the highest probability at every step. Output becomes deterministic (up to backend-specific tiebreaks).",
        "It makes it cold.",
    ),
    (
        "Why use chunking in RAG pipelines?",
        "Chunking splits long documents into smaller passages so retrieval can return focused, relevant context within the LLM's input budget. Chunk size and overlap trade retrieval precision vs. continuity.",
        "Because documents are long.",
    ),
    (
        "What is a tool-call in agent frameworks?",
        "A tool-call is a structured request from the LLM to invoke an external function (search, calculator, API), receive the result, and continue reasoning. Modern models emit tool-calls as JSON conforming to a declared schema.",
        "Calling a tool.",
    ),
]


def _judge(model, pair: tuple[str, str, str], swap: bool) -> str:
    q, a, b = pair
    if swap:
        prompt = JUDGE_PROMPT.format(question=q, a=b, b=a)
    else:
        prompt = JUDGE_PROMPT.format(question=q, a=a, b=b)
    raw = model.generate(prompt).strip().upper()
    for token in ("A", "B", "TIE"):
        if token in raw.split():
            return token
    if raw.startswith("A"):
        return "A"
    if raw.startswith("B"):
        return "B"
    return "TIE"


def _measure(model) -> dict[str, Any]:
    verdicts_normal: list[str] = []
    verdicts_swapped: list[str] = []
    for pair in PAIRS:
        verdicts_normal.append(_judge(model, pair, swap=False))
        verdicts_swapped.append(_judge(model, pair, swap=True))

    disagreements = 0
    per_pair = []
    for idx, (v1, v2) in enumerate(zip(verdicts_normal, verdicts_swapped)):
        # Суддя "узгоджений" якщо: (а) обирає ту саму *відповідь* (A→B при свопі = stability)
        # або (б) TIE в обох випадках.
        consistent = (v1, v2) in {("A", "B"), ("B", "A"), ("TIE", "TIE")}
        if not consistent:
            disagreements += 1
        per_pair.append(
            {"index": idx, "normal": v1, "swapped": v2, "consistent": consistent}
        )

    return {
        "model": model.get_model_name(),
        "disagreement_rate": disagreements / len(PAIRS),
        "per_pair": per_pair,
    }


def test_judge_position_bias() -> None:
    results = [_measure(PrimaryJudgeLLM())]
    if SECONDARY_AVAILABLE:
        results.append(_measure(SecondaryJudgeLLM()))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({"judges": results}, indent=2, ensure_ascii=False))

    for r in results:
        rate = r["disagreement_rate"]
        if rate > 0.30:
            import warnings

            warnings.warn(
                f"{r['model']} disagreement_rate={rate:.0%} > 30% — position bias likely. "
                "Consider jury-min aggregation for gating metrics.",
                stacklevel=1,
            )
        # Fail-loud тільки якщо совсім red flag рівень лекції.
        assert rate < 0.75, (
            f"{r['model']} disagreement_rate={rate:.0%} — judge unusable at this level"
        )
