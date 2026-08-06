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

#: Environment the operator sets so MCP runs are attributable. `dispatch` audits every run, but it can
#: only record the identity it is GIVEN — and until this existed the stdio transport passed none, so
#: every row in the governance console read actor `mcp` with no user and no pack. The audit trail
#: answered "which tools ran" and could not answer "whose agent ran them", which is the half an
#: enterprise actually asks for, both before granting access and after an incident.
ENV_USER = "AEC_MCP_USER"
ENV_ACTOR = "AEC_MCP_ACTOR"
ENV_PACK = "AEC_MCP_PACK"

#: What `actor` becomes when the operator sets nothing. Deliberately not a person-shaped default: a
#: placeholder like "local" or the OS username would put an unverified name in an audit trail, and a
#: name nobody authenticated is worse than an honest "the transport ran this".
TRANSPORT_ACTOR = "mcp-stdio"


def transport_identity(env: dict[str, str] | None = None) -> dict[str, object]:
    """The identity this transport can honestly claim, from the operator's environment.

    Pure and env-injectable so it is testable without the MCP SDK — the SDK is an optional dependency,
    so anything that can only be reached through `main()` cannot be covered by the suite at all.

    `attributed` is the field a console must read before showing a name. The stdio server has no
    authentication of its own: whoever can run the process can set these variables, so a configured
    user is an *operator assertion*, not a verified identity, and this says which one it is rather
    than letting a configured string pass for a login.
    """
    e = os.environ if env is None else env
    user = (e.get(ENV_USER) or "").strip() or None
    actor = (e.get(ENV_ACTOR) or "").strip() or TRANSPORT_ACTOR
    pack = (e.get(ENV_PACK) or "").strip() or None
    return {"actor": actor, "user": user, "pack": pack, "attributed": user is not None}


def _warn_unattributed(ident: dict[str, object], write=None) -> bool:
    """Say plainly, once at startup, that runs will not be attributable. Returns whether it warned.

    An unattributed audit trail must announce itself. Silently recording every run against the
    transport looks identical to recording it against a user nobody checked, and a console reading
    those rows cannot tell the difference either.
    """
    if ident["attributed"]:
        return False
    (write or sys.stderr.write)(
        f"massing-mcp: runs will be audited as {ident['actor']!r} with no user.\n"
        f"  Set {ENV_USER} (and optionally {ENV_PACK}) so the governance console can answer\n"
        f"  'whose agent ran this'. Without it the audit trail records what ran, not who ran it.\n")
    return True


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

    ident = transport_identity()
    _warn_unattributed(ident)

    def _make(tool: dict):
        def _run(**kwargs) -> str:
            db = SessionLocal()
            try:
                # Attribution is passed on EVERY run, not just write tools: "which tools did this
                # agent read from my project" is the question asked after an incident, and a read is
                # exactly what an exfiltration looks like.
                result = mcp_tools.dispatch(db, tool["name"], kwargs, actor=ident["actor"],
                                            user=ident["user"], pack=ident["pack"])
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
