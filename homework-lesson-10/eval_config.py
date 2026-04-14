"""Judge LLMs + Settings extensions for hw10 evaluation layer.

Primary judge = same vLLM that target agents use (Qwen3.5-35B).
Secondary judge = imaginary Qwen3-Next-80B-A3B-Instruct pod — when reachable,
enables LLM-as-a-Jury pattern for gating metrics (Correctness, Critique Quality,
Groundedness, Refusal Quality). When unreachable, suite falls back to primary-only.

README-compliance survives either mode — secondary is an enhancement.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

try:
    # Reuse hw8 settings factory via conftest-mounted sys.path.
    from config import Settings, create_llm  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "eval_config.py must be imported after conftest.py mounts sys.path "
        "(check sys.path includes PROJECT_ROOT and config.py is present)"
    ) from exc


SECONDARY_JUDGE_BASE = os.environ.get(
    "JUDGE_API_BASE", "http://uaai-qwen3-next.qwen3-chat.svc:8000/v1"
)
SECONDARY_JUDGE_KEY = os.environ.get("JUDGE_API_KEY", "not-needed")
SECONDARY_JUDGE_MODEL = os.environ.get(
    "JUDGE_MODEL", "Qwen3-Next-80B-A3B-Instruct"
)


def _secondary_available() -> bool:
    """Ping secondary judge endpoint. Non-raising."""
    try:
        r = httpx.get(
            f"{SECONDARY_JUDGE_BASE}/models",
            headers={"Authorization": f"Bearer {SECONDARY_JUDGE_KEY}"},
            timeout=3.0,
        )
        return r.status_code == 200
    except Exception:
        return False


SECONDARY_AVAILABLE = _secondary_available()


class _BaseJudge(DeepEvalBaseLLM):
    """Shared boilerplate between primary/secondary."""

    _client: ChatOpenAI

    def load_model(self) -> ChatOpenAI:
        return self._client

    def generate(self, prompt: str) -> str:
        return self._client.invoke(prompt).content

    async def a_generate(self, prompt: str) -> str:
        result = await self._client.ainvoke(prompt)
        return result.content


class PrimaryJudgeLLM(_BaseJudge):
    """Qwen3.5-35B-A3B — same target-family vLLM. Used for cheap metrics and as
    first judge in the jury. Residual self-enhancement/family bias is mitigated
    by pairing with SecondaryJudgeLLM for gating metrics."""

    def __init__(self) -> None:
        self._client = create_llm()

    def get_model_name(self) -> str:
        return "qwen3.5-35b-a3b (primary, target-family)"


class SecondaryJudgeLLM(_BaseJudge):
    """Qwen3-Next-80B-A3B-Instruct — separate pod, different scale/architecture.
    Different-snapshot weights reduce self-enhancement bias. Raises at
    instantiation if pod unreachable — callers should guard with SECONDARY_AVAILABLE."""

    def __init__(self) -> None:
        if not SECONDARY_AVAILABLE:
            raise RuntimeError(
                f"Secondary judge pod not reachable at {SECONDARY_JUDGE_BASE}. "
                "Run in primary-only mode or start the Qwen3-Next pod."
            )
        self._client = ChatOpenAI(
            base_url=SECONDARY_JUDGE_BASE,
            api_key=SecretStr(SECONDARY_JUDGE_KEY),
            model=SECONDARY_JUDGE_MODEL,
            temperature=0.0,
        )

    def get_model_name(self) -> str:
        return f"{SECONDARY_JUDGE_MODEL} (secondary, cross-scale)"


def jury(metric_factory, **kwargs) -> list[Any]:
    """Build metric instances bound to primary + (optional) secondary judge.

    `metric_factory` is typically a DeepEval metric class (GEval, FaithfulnessMetric, ...).
    Returns [primary] or [primary, secondary] depending on SECONDARY_AVAILABLE.

    Tests should aggregate with min() for strict gating:

        metrics = jury(GEval, name="Correctness", ...)
        scores = [m.measure(test_case) for m in metrics]
        assert min(scores) >= threshold
    """
    instances = [metric_factory(model=PrimaryJudgeLLM(), **kwargs)]
    if SECONDARY_AVAILABLE:
        instances.append(metric_factory(model=SecondaryJudgeLLM(), **kwargs))
    return instances


REASONING_PREAMBLE = (
    "Reason step by step about each criterion below before assigning a final "
    "score. Write your reasoning explicitly, then give the numeric score."
)
VERBOSITY_GUARD = "Do NOT consider response length in your evaluation."


def wrap_steps(steps: list[str]) -> list[str]:
    """Prepend reasoning-before-score + append verbosity guard to a custom
    GEval evaluation_steps list (Lesson 10, Block 3.2 + 3.3)."""
    return [REASONING_PREAMBLE, *steps, VERBOSITY_GUARD]
