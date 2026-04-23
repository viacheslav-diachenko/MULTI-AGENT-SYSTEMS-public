"""One-off: provision LLM Connection + 2 LLM-as-a-Judge evaluators in Langfuse.

Langfuse exposes the admin endpoints via tRPC, not the public REST API,
so we authenticate as the headless-init admin user, get a NextAuth session
cookie, and POST to ``/api/trpc/{llmApiKey,evals,job}.{create,...}``.

Run-once script. Idempotent-ish: if the LLM connection or templates
already exist with the same names, the script logs that and continues.

Usage:
    .venv/bin/python scripts/seed_evaluators.py \
        --base-url http://127.0.0.1:3001 \
        --project homework-12
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

import requests


ADMIN_EMAIL_SECRET = ("langfuse", "langfuse-init-secrets", "admin-email")
ADMIN_PASS_SECRET = ("langfuse", "langfuse-init-secrets", "admin-password")


def _kubectl_secret(ns: str, name: str, key: str) -> str:
    out = subprocess.check_output(
        ["kubectl", "-n", ns, "get", "secret", name, "-o", f"jsonpath={{.data.{key}}}"]
    )
    import base64

    return base64.b64decode(out).decode().strip()


def login(base: str, email: str, password: str) -> str:
    """Login via NextAuth credentials and return the path to a curl
    cookie jar with an active session token.

    We drive the whole flow via ``curl`` because NextAuth's CSRF
    double-submit check requires the exact same cookie on both the
    GET and the POST, and the cookie domain handling is brittle —
    curl's native jar works first-try.
    """
    import tempfile

    jar = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".cookies").name
    # GET csrf
    csrf_raw = subprocess.check_output(["curl", "-sS", "-c", jar, f"{base}/api/auth/csrf"])
    token = json.loads(csrf_raw)["csrfToken"]
    # POST credentials
    subprocess.check_output(
        [
            "curl", "-sS", "-b", jar, "-c", jar,
            "-X", "POST", f"{base}/api/auth/callback/credentials",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "--data-urlencode", f"csrfToken={token}",
            "--data-urlencode", f"email={email}",
            "--data-urlencode", f"password={password}",
            "--data-urlencode", f"callbackUrl={base}/",
            "-o", "/dev/null",
        ]
    )
    # verify session cookie made it in
    with open(jar) as f:
        jar_body = f.read()
    if "next-auth.session-token" not in jar_body:
        raise SystemExit("login: no session cookie after credentials POST")
    return jar


def trpc(jar: str, base: str, path: str, payload: dict[str, Any]) -> Any:
    """Call a tRPC mutation via ``curl``. tRPC v10 batched-input: index 0."""
    out = subprocess.check_output(
        [
            "curl", "-sS", "-b", jar,
            "-X", "POST", f"{base}/api/trpc/{path}?batch=1",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"0": {"json": payload}}),
        ]
    )
    body = json.loads(out)
    if isinstance(body, list) and body and "error" in body[0]:
        return {"error": body[0]["error"]["json"]["message"]}
    return body[0].get("result", {}).get("data", {}).get("json", {})


def trpc_query(jar: str, base: str, path: str, payload: dict[str, Any]) -> Any:
    import urllib.parse

    encoded = urllib.parse.quote(json.dumps({"0": {"json": payload}}))
    out = subprocess.check_output(
        ["curl", "-sS", "-b", jar, f"{base}/api/trpc/{path}?batch=1&input={encoded}"]
    )
    body = json.loads(out)
    if isinstance(body, list) and body and "error" in body[0]:
        return {"error": body[0]["error"]["json"]["message"]}
    return body[0].get("result", {}).get("data", {}).get("json", {})


# --- Evaluator definitions -------------------------------------------------

ANSWER_RELEVANCE_PROMPT = """You are an impartial evaluator scoring a multi-agent research assistant.

Inputs:
- User query: {{input}}
- Final assistant response: {{output}}

Task: Rate on a continuous scale from 0.0 to 1.0 how directly and completely the response addresses the user's query.

Reason step by step before producing your final score. Do NOT consider response length — long answers are not automatically better than short ones. Penalize off-topic content, missing facets of the query, and refusals when the topic is in-scope.

Return JSON with two fields: ``score`` (float 0..1) and ``reason`` (brief justification, 1-2 sentences)."""


CITATION_PRESENCE_PROMPT = """You are an impartial evaluator checking citation discipline.

Inputs:
- Final assistant response: {{output}}

Task: Determine whether the response contains at least one explicit source citation. A citation is a URL, an attributed source name (e.g. "according to the LangChain docs"), or a footnote-style reference. Inline link text without a URL does NOT count.

Return JSON with two fields: ``score`` (boolean — true if at least one citation is present, else false) and ``reason`` (brief justification)."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:3001")
    ap.add_argument("--project", default="homework-12")
    args = ap.parse_args()

    email = os.getenv("LANGFUSE_ADMIN_EMAIL") or _kubectl_secret(*ADMIN_EMAIL_SECRET)
    password = os.getenv("LANGFUSE_ADMIN_PASSWORD") or _kubectl_secret(*ADMIN_PASS_SECRET)

    print(f"login as {email} ...")
    jar = login(args.base_url, email, password)

    # --- Resolve LLM connection (already created in earlier step) ---
    keys = trpc_query(jar, args.base_url, "llmApiKey.all", {"projectId": args.project})
    if isinstance(keys, dict) and "error" in keys:
        print(f"FATAL: llmApiKey.all -> {keys['error']}")
        return 1
    print(f"  {keys.get('totalCount', 0)} LLM connections in project")

    judge_provider = "gemma-vllm"
    judge_model = "gemma-4-26b-a4b-it"

    # --- Create evaluator templates ---
    templates = [
        {
            "name": "answer_relevance",
            "prompt": ANSWER_RELEVANCE_PROMPT,
            "vars": ["input", "output"],
            "outputDefinition": {
                "type": "score",
                "name": "score",
                "description": "Continuous 0..1 relevance score",
            },
            "scoreType": "NUMERIC",
        },
        {
            "name": "citation_presence",
            "prompt": CITATION_PRESENCE_PROMPT,
            "vars": ["output"],
            "outputDefinition": {
                "type": "score",
                "name": "score",
                "description": "True if at least one citation is present, else false",
            },
            "scoreType": "BOOLEAN",
        },
    ]

    template_ids = {}
    for t in templates:
        payload = {
            "projectId": args.project,
            "name": t["name"],
            "prompt": t["prompt"],
            "vars": t["vars"],
            "outputDefinition": t["outputDefinition"],
            "provider": judge_provider,
            "model": judge_model,
            "modelParams": {},
        }
        out = trpc(jar, args.base_url, "evals.createTemplate", payload)
        if isinstance(out, dict) and "error" in out:
            print(f"  evals.createTemplate {t['name']} -> {out['error'][:200]}")
        else:
            tid = (out or {}).get("id")
            template_ids[t["name"]] = tid
            print(f"  template {t['name']} -> id={tid}")

    if not template_ids:
        print("\nNo templates created — see errors above.")
        return 1

    # --- Create job configurations (= evaluators that auto-run on traces) ---
    for name, tid in template_ids.items():
        if not tid:
            continue
        vars_for_job = ["input", "output"] if name == "answer_relevance" else ["output"]
        job = {
            "projectId": args.project,
            "evalTemplateId": tid,
            "scoreName": name,
            "filter": [{"column": "Tags", "operator": "any of", "type": "stringOptions", "value": ["hw12"]}],
            "target": "trace",
            "mapping": [
                {
                    "templateVariable": v,
                    "langfuseObject": "trace",
                    "selectedColumnId": v,
                    "jsonSelector": None,
                }
                for v in vars_for_job
            ],
            "sampling": 1.0,
            "delay": 30,
            "timeScope": ["NEW"],
        }
        out = trpc(jar, args.base_url, "evals.createJob", job)
        if isinstance(out, dict) and "error" in out:
            print(f"  evals.createJob {name} -> {out['error'][:200]}")
        else:
            print(f"  job {name} -> created ({out})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
