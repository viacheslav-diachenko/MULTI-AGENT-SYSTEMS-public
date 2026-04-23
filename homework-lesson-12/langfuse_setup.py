"""Langfuse client + LangChain callback + cached Prompt Management helper.

Single import surface for the whole MAS:

    from langfuse_setup import (
        langfuse_client,
        langfuse_callback,
        get_prompt_text,
        observe,
        propagate_attributes,
    )

`get_prompt_text` is the only place in the codebase that talks to the prompt
registry. It memoizes per process to avoid an HTTP round-trip on every agent
turn — restart the REPL after promoting a new prompt version.

The hw10 v1.0.4 lesson applies: timestamps that change every call (e.g.
`datetime.now()`) MUST be passed as `compile()` variables, not baked into the
prompt body stored in Langfuse — otherwise the stored body would have to be
re-published on every clock tick.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Langfuse SDK reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST
# straight from the process environment. pydantic-settings (used in config.py)
# only loads into Settings, not os.environ, so we load .env explicitly here
# before the singleton client is instantiated.
load_dotenv(Path(__file__).resolve().parent / ".env")

from langfuse import get_client, observe, propagate_attributes  # noqa: E402
from langfuse.langchain import CallbackHandler  # noqa: E402

__all__ = [
    "langfuse_client",
    "langfuse_callback",
    "get_prompt_text",
    "observe",
    "propagate_attributes",
]


langfuse_client = get_client()
langfuse_callback = CallbackHandler()


@lru_cache(maxsize=16)
def _fetch_prompt(name: str, label: str):
    return langfuse_client.get_prompt(name, label=label)


def get_prompt_text(name: str, *, label: str = "production", **variables) -> str:
    """Fetch a prompt from Langfuse Prompt Management and compile it.

    Args:
        name: Prompt name in Langfuse (e.g. ``"hw12/supervisor_system"``).
        label: Prompt label to fetch. Defaults to ``"production"``.
        **variables: Template variables for ``{{var}}`` placeholders.

    Raises:
        Whatever the Langfuse SDK raises when the prompt is missing — hw12
        Req #3 forbids hardcoded fallbacks, so a missing registry entry is
        treated as a deploy error.
    """
    return _fetch_prompt(name, label).compile(**variables)
