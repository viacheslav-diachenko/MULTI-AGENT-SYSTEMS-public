"""Startup health checks for MCP/ACP endpoints.

Pings SearchMCP, ReportMCP, and the ACP server before the REPL opens,
so connection / DNS / port issues surface immediately instead of
masquerading as obscure tool-call errors mid-conversation.

Usage:
    from health import run_health_checks
    results = run_health_checks(Settings())
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from acp_sdk.client import Client as ACPClient
from fastmcp import Client as FastMCPClient

from config import Settings

logger = logging.getLogger(__name__)


@dataclass
class HealthResult:
    name: str
    url: str
    ok: bool
    detail: str


async def _check_mcp(url: str, name: str) -> HealthResult:
    try:
        async with FastMCPClient(url) as client:
            tools = await client.list_tools()
        return HealthResult(name, url, True, f"{len(tools)} tools available")
    except Exception as exc:  # pragma: no cover — network dependent
        logger.warning("%s health check failed: %s", name, exc)
        return HealthResult(name, url, False, f"{type(exc).__name__}: {exc}")


async def _check_acp(url: str) -> HealthResult:
    try:
        async with ACPClient(
            base_url=url,
            headers={"Content-Type": "application/json"},
        ) as client:
            agents = [a async for a in client.agents()]
        names = ", ".join(a.name for a in agents) or "no agents"
        return HealthResult("ACP", url, True, f"{len(agents)} agents ({names})")
    except Exception as exc:  # pragma: no cover — network dependent
        logger.warning("ACP health check failed: %s", exc)
        return HealthResult("ACP", url, False, f"{type(exc).__name__}: {exc}")


async def _run_all(settings: Settings) -> list[HealthResult]:
    return await asyncio.gather(
        _check_mcp(settings.search_mcp_url, "SearchMCP"),
        _check_mcp(settings.report_mcp_url, "ReportMCP"),
        _check_acp(settings.acp_base_url),
    )


def run_health_checks(settings: Settings) -> list[HealthResult]:
    """Synchronous wrapper around the async health probes."""
    return asyncio.run(_run_all(settings))


def format_results(results: list[HealthResult]) -> str:
    """Produce a human-friendly summary for the REPL banner."""
    lines = []
    for r in results:
        marker = "OK " if r.ok else "FAIL"
        lines.append(f"  [{marker}] {r.name:<9} {r.url}  — {r.detail}")
    return "\n".join(lines)
