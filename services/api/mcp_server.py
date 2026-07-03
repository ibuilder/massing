"""MCP server — exposes a Massing project/model to an MCP client (Claude Desktop, Cursor, an agent).

Run it over stdio and point an MCP client at it; the client can then read a project's snapshot, records,
CDE / KPI / model-quality checks, run a standards-compliance check, and create an RFI — all against the
same engines the HTTP API uses. The Model Context Protocol SDK is an optional dependency (this platform
is offline-first and doesn't force it): if `mcp` isn't installed this prints how to enable it and exits.

    pip install "mcp[cli]"
    PYTHONPATH=src python mcp_server.py            # stdio server

Claude Desktop config (claude_desktop_config.json):
    {"mcpServers": {"massing": {"command": "python",
        "args": ["/path/to/services/api/mcp_server.py"],
        "env": {"PYTHONPATH": "/path/to/services/api/src",
                "DATABASE_URL": "postgresql://..."}}}}
"""
from __future__ import annotations

import json
import os
import sys


def _fail_no_sdk() -> None:
    sys.stderr.write(
        "The Model Context Protocol SDK is not installed.\n"
        "  pip install \"mcp[cli]\"\n"
        "then re-run:  PYTHONPATH=src python mcp_server.py\n"
        "(The tool logic in aec_api.mcp_tools works without the SDK; only the stdio server needs it.)\n")
    raise SystemExit(2)


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP           # type: ignore
    except ModuleNotFoundError:
        _fail_no_sdk()
        return

    os.environ.setdefault("DATABASE_URL", "sqlite:///./aec.db")
    from aec_api import mcp_tools
    from aec_api.db import SessionLocal

    server = FastMCP("massing")

    def _make(tool: dict):
        def _run(**kwargs) -> str:
            db = SessionLocal()
            try:
                result = mcp_tools.dispatch(db, tool["name"], kwargs)
                db.commit()
                return json.dumps(result, default=str)
            finally:
                db.close()
        _run.__name__ = tool["name"]
        _run.__doc__ = tool["description"]
        return _run

    # Register every catalog tool with the MCP server.
    for tool in mcp_tools.catalog():
        server.add_tool(_make(tool), name=tool["name"], description=tool["description"])

    server.run()


if __name__ == "__main__":
    main()
