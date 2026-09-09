"""R22-AGENT-PACKS — named agent packs over the tools we already ship, and per-run audit.

Premise-checked: `mcp_tools` exposes **18** tools with `dispatch()` and `catalog()`, and
`audit.record` exists. So this is packaging, exactly as the ring entry says — with one finding the
entry only implies:

**Originally 16 of the 18 tools ran with no audit trail** — `audit.record` was called inside
`_run_recipe`, for the IFC edit it performs, not for tool dispatch itself. `dispatch` now audits
every run, success and failure, so "which tools did this agent run against my project last week?"
has an answer. `run_log()` here reads that trail and is the per-run record the entry calls the
gating factor.

The second half took longer to see, because it was not in the callee. `dispatch` can only record the
identity it is **given**, and the stdio transport — the one path every real agent run takes — passed
none, so each row read actor `mcp` with no user and no pack. `test_agent_packs.py` asserted runs are
attributed "to the effective user, not the transport" and passed, because the test supplied a user
the transport never did. The trail answered *which tools ran* and not *whose agent ran them*, which
is the half an enterprise asks for. Fixed at the call site; `test_mcp_attribution.py` asserts the
call site forwards all three, since a test that supplies a caller's arguments cannot notice the
caller omitting them.

A pack is a **named view over existing tools**. That framing carries the refusals:

1. **a pack grants nothing.** It cannot contain a tool that is not already in `mcp_tools.TOOLS`, and
   membership confers no permission — `dispatch` still applies its own checks. A pack that could
   widen access would turn "Submittal Review Agent" into a privilege-escalation surface, which is
   the opposite of what a governance console is for;
2. **a pack naming an unknown tool is REFUSED, not silently trimmed.** A pack that quietly drops a
   tool looks like it worked and behaves like it did not — the superintendent runs "Submittal
   Review" and the submittal check simply never happens;
3. **write tools are named as write tools.** A pack containing `create_rfi` or `run_recipe` mutates
   the project, and a console that lists packs without saying which can write is a console nobody
   can govern with.
"""
from __future__ import annotations

from typing import Any

#: Named packs: a superintendent understands "Submittal Review", not `standards_check`. Each is a
#: subset of `mcp_tools.TOOLS` — see refusal 1. Ordering within a pack is the order a human would
#: work in, not alphabetical.
PACKS: dict[str, dict[str, Any]] = {
    "submittal_review": {
        "label": "Submittal Review Agent",
        "purpose": "check a submittal against the model and the project's standards before it is "
                   "returned to the subcontractor",
        "tools": ["project_snapshot", "standards_check", "openbim_quality", "model_quantities",
                  "create_rfi"],
    },
    "design_qa": {
        "label": "Design QA Agent",
        "purpose": "find what a coordination review would find: clashes, quality gaps and code "
                   "violations, with the drawings checked against the model",
        "tools": ["openbim_quality", "clash_results", "code_violations", "drawing_qa"],
    },
    "schedule_risk": {
        "label": "Schedule Risk Agent",
        "purpose": "the weekly look-ahead question — what is drifting, and what does the model say "
                   "about the work in front of it",
        "tools": ["computed_schedules", "schedule_risk", "project_snapshot"],
    },
    "permit_readiness": {
        "label": "Permit Readiness Agent",
        "purpose": "whether this project could be submitted for permit today, and what is missing",
        "tools": ["permit_readiness", "code_violations", "drawing_qa", "cde_status"],
    },
    "carbon_report": {
        "label": "Carbon Report Agent",
        "purpose": "embodied carbon from the model's own quantities, with the KPI context around it",
        "tools": ["model_quantities", "carbon_report", "bim_kpi_scorecard"],
    },
}


class PackError(ValueError):
    """A pack that would mislead — raised rather than trimmed."""


def _known() -> set[str]:
    from .mcp_tools import TOOL_NAMES
    return set(TOOL_NAMES)


def _write_tools() -> set[str]:
    from .mcp_tools import _WRITE_TOOLS
    return set(_WRITE_TOOLS)


def validate(packs: dict[str, dict] | None = None) -> dict[str, Any]:
    """Every pack's tools must exist. A pack naming an unknown tool is a defect, not a warning.

    Refused rather than trimmed: a pack that silently drops a tool looks like it worked and behaves
    like it did not, which is worse than a pack that will not load.
    """
    packs = packs if packs is not None else PACKS
    known = _known()
    problems = []
    for key, p in packs.items():
        unknown = [t for t in (p.get("tools") or []) if t not in known]
        if unknown:
            problems.append({"pack": key, "unknown_tools": unknown,
                             "note": f"pack {key!r} names tool(s) that do not exist in mcp_tools"})
        if not (p.get("tools") or []):
            problems.append({"pack": key, "unknown_tools": [],
                             "note": f"pack {key!r} contains no tools — an empty agent is a label"})
    return {"ok": not problems, "problems": problems, "pack_count": len(packs),
            "tool_count": len(known)}


def catalog() -> dict[str, Any]:
    """The governance console's list: packs, what each runs, and which of them can WRITE."""
    v = validate()
    if not v["ok"]:
        raise PackError(f"agent pack catalog is invalid: {v['problems']}")
    writes = _write_tools()
    out = []
    for key in PACKS:
        # `tools_for`, not `list(p["tools"])` inlined — the accessor existed and had no caller, which
        # is what made it look dead. The keys come from PACKS here so its unknown-pack refusal cannot
        # fire, and that is fine: the point is one definition of "what a pack runs", not a new guard.
        tools = tools_for(key)
        p = PACKS[key]
        w = [t for t in tools if t in writes]
        out.append({
            "key": key, "label": p["label"], "purpose": p["purpose"], "tools": tools,
            "tool_count": len(tools),
            "writes": bool(w), "write_tools": w,
            "note": ("this pack can MODIFY the project — " + ", ".join(w) if w
                     else "read-only: this pack cannot modify the project"),
        })
    out.sort(key=lambda r: r["key"])
    return {
        "packs": out, "pack_count": len(out),
        "read_only_count": sum(1 for r in out if not r["writes"]),
        "note": ("a pack is a named VIEW over tools that already exist — it grants nothing. Every "
                 "tool in every pack is in mcp_tools.TOOLS, and dispatch applies its own checks "
                 "regardless of which pack a caller came in through."),
    }


def tools_for(pack: str) -> list[str]:
    """The tool names a pack runs. Raises on an unknown pack rather than returning an empty list —
    an empty list reads as "this pack does nothing", which is a different and wrong answer."""
    p = PACKS.get(pack)
    if p is None:
        raise PackError(f"unknown agent pack {pack!r}; known: {sorted(PACKS)}")
    return list(p["tools"])


def run_log(db, project_id: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Per-run tool history — the record the ring entry calls the gating factor for enterprise use.

    Reads the audit log rather than a second store, so it cannot disagree with the audit trail. Both
    successes AND failures are reported: an agent log that shows only what worked cannot answer
    "what did it try?", which is the question asked after an incident rather than before one.
    """
    from .models import AuditLog

    q = db.query(AuditLog).filter(AuditLog.method == "MCP")
    if project_id:
        # THE PROJECT FILTER MUST RUN IN SQL, BEFORE THE LIMIT. It used to be a Python `continue`
        # after `.limit(limit)` had already truncated to the newest rows across EVERY project, so a
        # quiet project on a busy install reported **zero runs while runs existed** — measured: one
        # run on project A, 250 newer runs on project B, and A's console answered "nothing ran".
        # For a governance console that is not a blank, it is a wrong answer: "no agent touched this
        # project" is exactly the claim someone relies on before granting access or after an
        # incident. Busy projects lost rows too (B returned 200 of its 250).
        #
        # `detail["project_id"].as_string()` compiles to json_extract on SQLite and ->> on
        # Postgres, so one expression covers the test dialect and the production one. A row whose
        # detail carries no project_id yields NULL and is excluded, which is what the old Python
        # comparison against "" did — the semantics are unchanged, only the stage they run at.
        q = q.filter(AuditLog.detail["project_id"].as_string() == project_id)
    # How many runs there ARE, before the window. A console that caps at `limit` and says nothing
    # reports "these are the runs" when it means "these are the newest N" — the same
    # partial-answer-wearing-a-complete-answer's-costume the fix above is about, one layer down.
    total = q.count()
    rows = q.order_by(AuditLog.ts.desc()).limit(limit).all()
    runs = []
    for r in rows:
        d = r.detail or {}
        runs.append({"ts": getattr(r.ts, "isoformat", lambda: None)(), "actor": r.actor,
                     "action": r.action, "tool": d.get("tool"), "pack": d.get("pack"),
                     "ok": d.get("ok"), "project_id": d.get("project_id")})
    by_tool: dict[str, int] = {}
    # `by_actor` is the axis that only matters once the log spans projects: across an estate the
    # governance question is *who ran an agent*, and a tally of tools cannot answer it. An
    # unattributed run is counted under an explicit "(unattributed)" rather than dropped — the
    # transport refuses to invent a person-shaped default, so those rows exist and hiding them
    # would understate exactly the runs a reviewer most needs to see.
    by_actor: dict[str, int] = {}
    for x in runs:
        if x.get("tool"):
            by_tool[x["tool"]] = by_tool.get(x["tool"], 0) + 1
        who = x.get("actor") or "(unattributed)"
        by_actor[who] = by_actor.get(who, 0) + 1
    failures = [x for x in runs if x.get("ok") is False]
    return {"runs": runs, "run_count": len(runs), "by_tool": by_tool, "by_actor": by_actor,
            "failure_count": len(failures),
            # `run_total` counts every matching run; `run_count` is what this window holds. They
            # differ only when `truncated`, and a caller that shows one while meaning the other is
            # the reason both are here rather than just the list's length.
            "run_total": total, "truncated": total > len(runs),
            "note": ("failures are included deliberately — a tool history that lists only successes "
                     "cannot answer what an agent attempted, which is the question asked after an "
                     "incident rather than before one."),
            }
