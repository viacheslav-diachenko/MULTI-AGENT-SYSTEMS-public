"""ReportMCP — FastMCP server exposing the save_report tool.

Tools:
    - save_report — write Markdown report into OUTPUT_DIR

Resources:
    - resource://output-dir — absolute path plus list of stored reports

Run standalone:
    python mcp_servers/report_mcp.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP

from config import Settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

settings = Settings()
mcp = FastMCP(name="ReportMCP")


@mcp.tool
def save_report(filename: str, content: str) -> str:
    """Save a Markdown report to the output directory.

    The filename is sanitised to a basename and forced to end with ``.md``.
    Returns the absolute path of the written file on success.
    """
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    output_dir = settings.output_dir
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, safe_name)
    try:
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as e:
        logger.error("save_report failed for path=%r: %s", filepath, e)
        # Fail loud: let FastMCP surface the error as a protocol error so
        # the Supervisor wrapper propagates it to LangGraph as a tool
        # failure instead of a success-shaped string the REPL truncates.
        raise RuntimeError(f"Failed to save report to {filepath}: {e}") from e

    abs_path = os.path.abspath(filepath)
    logger.info("Report saved: %s", abs_path)
    return f"Report saved successfully: {abs_path}"


@mcp.resource("resource://output-dir")
def output_dir_info() -> str:
    """Return the absolute output directory path and a list of stored reports."""
    output_dir = settings.output_dir
    absolute = os.path.abspath(output_dir)
    reports: list[dict] = []
    if os.path.isdir(output_dir):
        for name in sorted(os.listdir(output_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(output_dir, name)
            try:
                size = os.path.getsize(path)
                mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
            except OSError:
                continue
            reports.append({"filename": name, "size_bytes": size, "modified": mtime})

    return json.dumps(
        {"output_dir": absolute, "report_count": len(reports), "reports": reports},
        ensure_ascii=False,
        indent=2,
    )


def main() -> None:  # pragma: no cover — entry point
    logger.info("Starting ReportMCP on %s:%d", settings.report_mcp_host, settings.report_mcp_port)
    mcp.run(
        transport="streamable-http",
        host=settings.report_mcp_host,
        port=settings.report_mcp_port,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
