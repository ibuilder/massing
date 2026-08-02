"""Generic dispatchers must classify every operation they will run.

The threat model lists "privilege escalation via side doors" (HARDEN-2) and, unusually for that
document, names its own enforcement honestly: *"Checked in hand-audit passes."* Two dispatchers carry
the risk, and each keeps a hand-maintained privilege table beside a registry that grows on its own:

    routers/jobs.py   _KIND_MIN_ROLE  -> 1 entry, against 7 registered job kinds
    mcp_tools.py      _WRITE_TOOLS    -> 2 entries, against 18 registered tools

**Both tables are correct today** — this test fixes no live defect, and should not be read as though
it did. `escalation_scan` is the one job kind needing more than the generic `editor` gate, and
`create_rfi`/`run_recipe` are genuinely the only MCP tools that write (checked: the other `db`-taking
tools — `permit_check.readiness`, `drawing_qa.review`, `standards_expert.check` — perform no writes).

What is missing is not a check on today's entries but a reason tomorrow's must exist. A dispatcher is
the one place where adding a feature grants a capability *without touching an authorisation decision*:
register a kind, and it is reachable at `editor`; add a tool, and it dispatches without the write
gate. The route table has `test_route_authz` walking it precisely because that population grows; these
two had nothing, which is the `_PROTECTED_PREFIXES` story again — that list was also correct on the
day it was written, and four holes entered through the space it did not cover.

So every operation must be classified, and the classification is frozen here rather than in the
dispatcher: the sets record "this existed and somebody looked at it", never "this is safe". Three
ways to fail, all mutation-verified below:

  1. an operation registered and classified NOWHERE      -> the actual bug this exists to catch
  2. a frozen entry with no referent                     -> a stale name pre-authorising whatever
                                                            reuses it, which is how an allowlist rots
  3. a MUTATING job kind that is neither elevated nor    -> the sharp case: `_MUTATING_KINDS` is
     explicitly acknowledged as editor-sufficient           derived from the code, so a kind that
                                                            starts writing is caught even if its
                                                            name never changes

(3) is the one a plain membership check would wave through, and it is the reason this reads
`_MUTATING_KINDS` rather than trusting the frozen list alone.

Kinds and tools register on import, so the app must actually be started — `app.routes` at import time
sees a fraction of the real surface, and the same is true here.
"""
import sys

from fastapi.testclient import TestClient

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# --- frozen classifications ---------------------------------------------------------
# A job kind the generic editor gate is sufficient for. The reason is the whole entry: it records
# WHY editor is enough, which is what a reviewer needs to judge whether it still is.
EDITOR_OK_KINDS = {
    "echo": "diagnostic no-op; touches nothing",
    "clash_detect": "read-only analysis over the loaded model",
    "cobie_export": "derives an export artifact; no project state written",
    "compiled_set_pdf": "renders a drawing set; no project state written",
    "model_export": "derives an export artifact; no project state written",
    "model_ci": "MUTATING, but its direct route POST /projects/{pid}/ci/run is also editor — the "
                "queue is therefore not a side door around a stricter endpoint",
}
# MCP tools that only read. Same contract: listed means looked at, not means safe.
READ_ONLY_TOOLS = {
    "list_projects", "project_snapshot", "list_records", "cde_status", "bim_kpi_scorecard",
    "openbim_quality", "standards_check", "list_recipes", "schedule_risk", "carbon_report",
    "permit_readiness", "drawing_qa", "model_quantities", "computed_schedules", "clash_results",
    "code_violations",
}


def classify_problems(kinds, mutating, elevated, editor_ok, tools, write_tools, read_only):
    """Injectable so every rule can be driven with a synthetic violation. Returns problems."""
    problems = []
    for k in sorted(set(kinds)):
        if k not in elevated and k not in editor_ok:
            problems.append(f"job kind {k!r} is registered but classified nowhere — add it to "
                            f"_KIND_MIN_ROLE, or to EDITOR_OK_KINDS with the reason editor suffices")
    for k in sorted(set(editor_ok) - set(kinds)):
        problems.append(f"EDITOR_OK_KINDS names {k!r}, which is not a registered job kind — remove "
                        f"it so the name cannot pre-authorise a future kind that reuses it")
    for k in sorted(set(mutating) - set(elevated) - set(editor_ok)):
        problems.append(f"job kind {k!r} MUTATES but is neither elevated nor acknowledged")
    for t in sorted(set(tools)):
        if t not in write_tools and t not in read_only:
            problems.append(f"MCP tool {t!r} is registered but classified nowhere — add it to "
                            f"_WRITE_TOOLS, or to READ_ONLY_TOOLS")
    for t in sorted(set(read_only) - set(tools)):
        problems.append(f"READ_ONLY_TOOLS names {t!r}, which is not a registered tool — remove it")
    return problems


# --- the live dispatchers -----------------------------------------------------------
from aec_api.main import app  # noqa: E402

with TestClient(app):
    from aec_api import jobs, mcp_tools
    from aec_api.routers import jobs as jobs_router

    live = classify_problems(jobs.KINDS, jobs._MUTATING_KINDS, jobs_router._KIND_MIN_ROLE,
                             EDITOR_OK_KINDS, mcp_tools.TOOL_NAMES, mcp_tools._WRITE_TOOLS,
                             READ_ONLY_TOOLS)
    check("every job kind and MCP tool is classified", not live, "; ".join(live))
    check("and the populations are non-trivial, so this is not vacuous",
          len(jobs.KINDS) >= 5 and len(mcp_tools.TOOL_NAMES) >= 10,
          f"{len(jobs.KINDS)} kinds, {len(mcp_tools.TOOL_NAMES)} tools")

    # the elevated table must still mean something: every name in it must be a real kind
    stale = sorted(set(jobs_router._KIND_MIN_ROLE) - set(jobs.KINDS))
    check("_KIND_MIN_ROLE has no entry without a referent", not stale, str(stale))

    # every write tool must be a real tool (a typo'd name silently disables its gate)
    stale_w = sorted(set(mcp_tools._WRITE_TOOLS) - set(mcp_tools.TOOL_NAMES))
    check("_WRITE_TOOLS has no entry without a referent — a typo here silently removes the gate",
          not stale_w, str(stale_w))

# --- each rule must be able to go red ------------------------------------------------
BASE = {"kinds": {"a"}, "mutating": set(), "elevated": {}, "editor_ok": {"a": "r"},
        "tools": {"t"}, "write_tools": set(), "read_only": {"t"}}

def drive(**over):
    return classify_problems(**{**BASE, **over})

check("fires on an unclassified job kind — the new-kind case",
      len(drive(kinds={"a", "brand_new"})) == 1, str(drive(kinds={"a", "brand_new"})))
check("fires on an unclassified MCP tool",
      len(drive(tools={"t", "brand_new"})) == 1)
check("fires on a frozen kind with no referent",
      len(drive(editor_ok={"a": "r", "deleted": "r"})) == 1)
check("fires on a frozen tool with no referent",
      len(drive(read_only={"t", "deleted"})) == 1)
check("fires on a kind that MUTATES but is only editor-classified — even with its name unchanged",
      len(drive(kinds={"a", "m"}, mutating={"m"}, editor_ok={"a": "r"})) == 2,
      str(drive(kinds={"a", "m"}, mutating={"m"}, editor_ok={"a": "r"})))
check("a mutating kind IS satisfied by an explicit acknowledgement",
      drive(kinds={"a", "m"}, mutating={"m"}, editor_ok={"a": "r", "m": "reason"}) == [])
check("clean input yields no problems — the detector is not just return-a-list", drive() == [])

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("dispatcher_privilege_coverage OK — every job kind and MCP tool classified; "
      "6 failure modes verified red")
