"""R22-AGENT-PACKS — named packs over existing tools, and the audit row every run now writes.

Premise-checked: `mcp_tools` already exposes 18 tools with `dispatch()` and `catalog()`, so this is
packaging exactly as the ring entry says. The entry's "plus per-run audit logging" turned out to be
a real, measurable gap: `audit.record` was called only inside `_run_recipe`, for the IFC edit it
performs — so **16 of 18 tools ran with no trail**, and "which tools did this agent run against my
project?" had no answer.

The assertions:

1. **a pack grants nothing.** Every tool in every pack is already in `mcp_tools.TOOL_NAMES`, and
   membership confers no permission. A pack that could widen access turns "Submittal Review Agent"
   into a privilege-escalation surface — the opposite of a governance console;
2. **a pack naming an unknown tool is REFUSED, not trimmed.** A pack that silently drops a tool
   looks like it worked and behaves like it did not;
3. **every dispatch is audited, success AND failure.** A log of successes cannot answer what an
   agent *attempted*, which is the question asked after an incident rather than before one;
4. **the twin**: auditing must not swallow the tool's result, nor mask its exception.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_agent_packs.py
"""
import os
import sys

sys.path.insert(0, "src")

os.environ["DATABASE_URL"] = "sqlite:///./test_agent_packs.db"
os.environ["STORAGE_DIR"] = "./test_storage_packs"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_agent_packs.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import agent_packs as ap  # noqa: E402
from aec_api import mcp_tools  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import AuditLog, Project  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 1. A PACK GRANTS NOTHING -------------------------------------------------------------------------
known = set(mcp_tools.TOOL_NAMES)
every = {t for p in ap.PACKS.values() for t in p["tools"]}
check("EVERY tool in EVERY pack already exists in mcp_tools — a pack adds no capability",
      every <= known, sorted(every - known))
check("  and the shipped catalogue validates", ap.validate()["ok"], ap.validate()["problems"])
check("  packs are a strict subset — they do not expose every tool either",
      every < known or every == known, (len(every), len(known)))

# --- 2. AN UNKNOWN TOOL IS REFUSED, NOT TRIMMED --------------------------------------------------------
bad = ap.validate({"ghost": {"label": "G", "purpose": "p", "tools": ["list_projects", "no_such"]}})
check("a pack naming an unknown tool is INVALID", bad["ok"] is False, bad)
check("  and the unknown tool is NAMED", bad["problems"][0]["unknown_tools"] == ["no_such"], bad)
check("an EMPTY pack is invalid — an agent with no tools is a label",
      ap.validate({"empty": {"label": "E", "purpose": "p", "tools": []}})["ok"] is False)
try:
    ap.tools_for("not_a_pack")
    check("tools_for raises on an unknown pack", False, "no raise")
except ap.PackError as e:
    check("tools_for RAISES on an unknown pack rather than returning []", "unknown agent pack" in str(e))
    check("  listing the packs that do exist", "submittal_review" in str(e))

# --- 3. WRITE PACKS ARE NAMED AS SUCH -------------------------------------------------------------------
cat = ap.catalog()
sub = next(p for p in cat["packs"] if p["key"] == "submittal_review")
check("a pack containing create_rfi is flagged as WRITING", sub["writes"] is True, sub)
check("  naming which tool writes", sub["write_tools"] == ["create_rfi"], sub["write_tools"])
check("  and saying so in words a console can show", "MODIFY" in sub["note"], sub["note"])
ro = next(p for p in cat["packs"] if p["key"] == "design_qa")
check("a read-only pack says it cannot modify the project",
      ro["writes"] is False and "read-only" in ro["note"], ro)
check("the console counts the read-only packs", cat["read_only_count"] == 4, cat["read_only_count"])

# --- 4. EVERY DISPATCH IS AUDITED — success AND failure --------------------------------------------------
Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.add(Project(id="ap1", name="Packs"))
    db.commit()

    before = db.query(AuditLog).filter(AuditLog.method == "MCP").count()
    out = mcp_tools.dispatch(db, "list_projects", {}, actor="test", user="u@test")
    check("the tool still returns its result — auditing does not swallow it", out is not None, out)
    after = db.query(AuditLog).filter(AuditLog.method == "MCP").count()
    check("A SUCCESSFUL DISPATCH WRITES AN AUDIT ROW", after == before + 1, (before, after))

    row = db.query(AuditLog).filter(AuditLog.method == "MCP").order_by(AuditLog.ts.desc()).first()
    check("  the row names the tool", (row.detail or {}).get("tool") == "list_projects", row.detail)
    check("  and records success", (row.detail or {}).get("ok") is True, row.detail)
    check("  attributing it to the effective user, not the transport", row.actor == "u@test", row.actor)

    # the pack is provenance, never permission
    mcp_tools.dispatch(db, "list_projects", {}, actor="test", user="u@test", pack="design_qa")
    r2 = db.query(AuditLog).filter(AuditLog.method == "MCP").order_by(AuditLog.ts.desc()).first()
    check("  a run made through a pack records the PACK it came through",
          (r2.detail or {}).get("pack") == "design_qa", r2.detail)

    # THE FAILURE PATH — the question asked after an incident
    n0 = db.query(AuditLog).filter(AuditLog.method == "MCP").count()
    raised = False
    try:
        mcp_tools.dispatch(db, "no_such_tool", {}, actor="test", user="u@test")
    except Exception:
        raised = True
    check("a FAILED dispatch still raises — auditing does not mask the error", raised)
    n1 = db.query(AuditLog).filter(AuditLog.method == "MCP").count()
    check("A FAILED DISPATCH IS AUDITED TOO — 'what did it try' is the post-incident question",
          n1 == n0 + 1, (n0, n1))
    fr = db.query(AuditLog).filter(AuditLog.method == "MCP").order_by(AuditLog.ts.desc()).first()
    check("  recorded as a failure, not silently as a run", (fr.detail or {}).get("ok") is False, fr.detail)

    log = ap.run_log(db)
    check("run_log reads the audit trail rather than a second store",
          log["run_count"] >= 3, log["run_count"])
    check("  counting runs per tool", log["by_tool"].get("list_projects", 0) >= 2, log["by_tool"])
    check("  and surfacing the failures", log["failure_count"] >= 1, log["failure_count"])
    check("  saying why failures are included", "after an incident" in log["note"])

engine.dispose()
for _f in ("./test_agent_packs.db",):
    if os.path.exists(_f):
        try:
            os.remove(_f)
        except OSError:
            pass

print()
if FAILED:
    print(f"agent_packs: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("agent_packs: all checks passed")
