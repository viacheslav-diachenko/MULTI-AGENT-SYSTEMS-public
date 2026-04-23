"""Run the 2 evaluators (answer_relevance + citation_presence) manually on
a trace set.

Context (hw12 Obмеження):
Langfuse 3.x processes OpenTelemetry-ingested traces via a different code
path from its SDK-native ``/api/public/ingestion`` endpoint. The OTEL path
does NOT fire the ``trace-upsert`` → ``create-eval-queue`` →
``evaluation-execution-queue`` chain, so online evaluators never run.
The SDK we use emits OTLP, so we hit this gap.

Fix-in-prod-later: when Langfuse closes this gap (or when we switch to
their v2 ingestion), the online evaluators configured in Langfuse UI take
over automatically — nothing in the MAS code has to change.

Workaround for hw12 delivery: this script fetches recent hw12 traces,
calls Gemma 4 directly with the same evaluation prompts that the online
evaluators use, and attaches the results as ``scores`` via
``langfuse_client.create_score``. Scores show up under each trace's
"Scores" tab identically to what the online evaluator would produce.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402
from langfuse_setup import langfuse_client  # noqa: E402

LANGFUSE_BASE = "http://127.0.0.1:3001"
JUDGE_BASE = "http://127.0.0.1:8001/v1"   # Qwen3.6 (or Gemma via vllm19); port-forwarded
JUDGE_MODEL = "qwen3.6-35b-a3b"            # use the main chat model for sanity — Gemma via PF would also work


ANSWER_RELEVANCE_PROMPT = """You are an impartial evaluator scoring a multi-agent research assistant.

Inputs:
- User query: {input}
- Final assistant response: {output}

Task: Rate on a continuous scale from 0.0 to 1.0 how directly and completely the response addresses the user's query.

Reason step by step before producing your final score. Do NOT consider response length — long answers are not automatically better than short ones. Penalize off-topic content, missing facets of the query, and refusals when the topic is in-scope.

Return JSON with two fields: ``score`` (float 0..1) and ``reason`` (brief justification, 1-2 sentences)."""


CITATION_PRESENCE_PROMPT = """You are an impartial evaluator checking citation discipline.

Inputs:
- Final assistant response: {output}

Task: Determine whether the response contains at least one explicit source citation. A citation is a URL, an attributed source name (e.g. "according to the LangChain docs"), or a footnote-style reference. Inline link text without a URL does NOT count.

Return JSON with two fields: ``score`` (boolean — true if at least one citation is present, else false) and ``reason`` (brief justification)."""


def _fetch_traces(public_key: str, secret_key: str, limit: int = 20):
    r = requests.get(
        f"{LANGFUSE_BASE}/api/public/traces?limit={limit}",
        auth=(public_key, secret_key),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]


def _call_judge(prompt: str) -> dict:
    """POST chat.completions with tool-call schema and parse returned JSON."""
    schema = {
        "type": "object",
        "properties": {
            "score": {"description": "Numeric 0..1 or boolean, depending on the evaluator"},
            "reason": {"type": "string"},
        },
        "required": ["score", "reason"],
    }
    payload = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "submit_score",
                    "description": "Submit the evaluator score and reasoning",
                    "parameters": schema,
                },
            }
        ],
        "tool_choice": "auto",
        "temperature": 0.0,
        "max_tokens": 600,
    }
    r = requests.post(f"{JUDGE_BASE}/chat/completions", json=payload, timeout=60)
    r.raise_for_status()
    choice = r.json()["choices"][0]["message"]
    if choice.get("tool_calls"):
        args = choice["tool_calls"][0]["function"]["arguments"]
        return json.loads(args)
    # Fallback: parse JSON from content — pull out the first top-level {...} block
    txt = choice.get("content") or ""
    start = txt.find("{")
    end = txt.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError(f"judge returned no JSON: {txt[:200]}")
    return json.loads(txt[start : end + 1])


def _flatten_text(obj) -> str:
    """Pull readable text out of Langfuse input/output blobs which can be
    dicts (kwargs payload) or lists of messages."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        # Common shape: {"args": [...], "kwargs": {...}}
        parts = []
        for key in ("content", "text"):
            if isinstance(obj.get(key), str):
                return obj[key]
        for v in obj.values():
            parts.append(_flatten_text(v))
        return " ".join(p for p in parts if p)
    if isinstance(obj, list):
        return " ".join(_flatten_text(i) for i in obj)
    return str(obj)


def main() -> int:
    import os

    pk = os.environ["LANGFUSE_PUBLIC_KEY"]
    sk = os.environ["LANGFUSE_SECRET_KEY"]

    traces = _fetch_traces(pk, sk, limit=20)
    scored = 0

    for t in traces:
        tags = t.get("tags") or []
        if "hw12" not in tags:
            continue
        input_txt = _flatten_text(t.get("input"))
        output_txt = _flatten_text(t.get("output"))
        if not input_txt or not output_txt:
            print(f"  skip {t['id'][:10]}: missing input/output")
            continue

        print(f"scoring {t['id'][:10]} (session {t.get('sessionId','?')[:15]})")

        try:
            ar = _call_judge(ANSWER_RELEVANCE_PROMPT.format(input=input_txt, output=output_txt))
            score_val = ar.get("score")
            if isinstance(score_val, str):
                score_val = float(score_val.strip())
            score_val = max(0.0, min(1.0, float(score_val)))
            langfuse_client.create_score(
                trace_id=t["id"],
                name="answer_relevance",
                value=score_val,
                comment=str(ar.get("reason", ""))[:250],
            )
            print(f"  answer_relevance = {score_val:.2f}")
            scored += 1
        except Exception as e:
            print(f"  answer_relevance failed: {e}")

        try:
            cp = _call_judge(CITATION_PRESENCE_PROMPT.format(output=output_txt))
            cv = cp.get("score")
            if isinstance(cv, str):
                cv = cv.lower().strip() in ("true", "yes", "1")
            langfuse_client.create_score(
                trace_id=t["id"],
                name="citation_presence",
                value=bool(cv),
                data_type="BOOLEAN",
                comment=str(cp.get("reason", ""))[:250],
            )
            print(f"  citation_presence = {bool(cv)}")
            scored += 1
        except Exception as e:
            print(f"  citation_presence failed: {e}")

    langfuse_client.flush()
    print(f"\ndone — {scored} scores attached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
