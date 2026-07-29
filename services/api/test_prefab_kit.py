"""R23-PREFAB-KIT — a kit is a frozen list, not a live query.

The join (scope + BOM + pull task + delivery) is the easy half. The half worth testing is the
conflict at the centre of it: a `query_dsl` selector re-evaluates against whatever the model says
today, and a kit is fabricated off-site against a scope decided weeks ago. Resolve that the
convenient way — always re-run the selector — and a model revision silently changes what the shop is
building after the steel is cut.

So the assertions here are mostly about which list is authoritative when, and about the two kinds of
drift being reported separately, because they are different defects: an element that has ENTERED the
selector's scope is work nobody priced; one that has LEFT it is a design change the shop has not been
told about and may already have built.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_prefab_kit.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import prefab_kit as pk  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def el(guid, cls, type_name=None, storey=None, qtos=None):
    return {"guid": guid, "ifc_class": cls, "name": guid, "type_name": type_name,
            "storey": storey, "psets": {}, "qtos": qtos or {}}


IDX = {
    "g1": el("g1", "IfcDuctSegment", "600x300", "L3",
             {"Qto_DuctSegmentBaseQuantities": {"Length": 4.0, "GrossArea": 2.4}}),
    "g2": el("g2", "IfcDuctSegment", "600x300", "L3",
             {"Qto_DuctSegmentBaseQuantities": {"Length": 6.0, "GrossArea": 3.6}}),
    "g3": el("g3", "IfcDuctFitting", "Elbow-90", "L3", {}),          # no base quantities at all
    "g4": el("g4", "IfcDuctSegment", "400x200", "L2",
             {"Qto_DuctSegmentBaseQuantities": {"Length": 3.0}}),
    "g5": el("g5", "IfcPipeSegment", "DN50", "L3",
             {"Qto_PipeSegmentBaseQuantities": {"Length": 9.0}}),
}

# --- 1. scope resolution -------------------------------------------------------------------------
r = pk.resolve(IDX, "IfcDuctSegment & storey=L3")
check("a selector resolves to the matching GUIDs", sorted(r["guids"]) == ["g1", "g2"], r["guids"])
bad = pk.resolve(IDX, "&&&")
check("a bad selector returns an error rather than raising",
      bad.get("error") and bad["guids"] == [], bad)
check("  because one broken kit must not fail a register of twelve", "bad selector" in bad["error"])
check("an empty selector is an error too", pk.resolve(IDX, "  ").get("error") == "no selector set")
check("with no model loaded nothing matches, and it says so",
      pk.resolve(None, "IfcDuctSegment")["matched"] == 0)

# --- 2. the BOM reads quantities from where they actually live ------------------------------------
# The index nests IFC quantity sets under `qtos`. Reading them as flat per-element keys returns a
# BOM of zeroes that is indistinguishable from a measured result — which is why this is asserted on
# real numbers rather than on "a quantity is present".
b = pk.bom(IDX, ["g1", "g2", "g3"])
check("BOM groups by class and type", len(b["lines"]) == 2, [ln["ifc_class"] for ln in b["lines"]])
duct = next(ln for ln in b["lines"] if ln["ifc_class"] == "IfcDuctSegment")
check("  the duct line counts both segments", duct["count"] == 2)
check("  and sums their declared length (4 + 6)", duct.get("length") == 10.0, duct.get("length"))
check("  and their area (2.4 + 3.6)", duct.get("area") == 6.0, duct.get("area"))
check("  totals roll up across lines", b["totals"]["count"] == 3 and b["totals"]["length"] == 10.0,
      b["totals"])
fitting = next(ln for ln in b["lines"] if ln["ifc_class"] == "IfcDuctFitting")
check("an element with no base quantities still counts", fitting["count"] == 1)
check("  but contributes NO length — absent, not zero", "length" not in fitting)
check("  and the BOM says how many were unquantified", b["unquantified"] == 1)
check("  in words, so a short total is not read as a measured one", "count only" in b["note"])
check("the BOM states what it measured", "declared" in b["measured"] and "no geometry" in b["measured"])

missing = pk.bom(IDX, ["g1", "ghost"])
check("a GUID not in the model is reported unresolved, not skipped",
      missing["unresolved"] == ["ghost"], missing["unresolved"])

# --- 3. drift — the point of the whole module -----------------------------------------------------
d = pk.drift(["g1", "g2"], ["g1", "g2"])
check("an unchanged scope has not drifted", d["drifted"] is False and d["stable"] == 2)
d2 = pk.drift(["g1", "g2"], ["g1", "g2", "g3"])
check("an element that JOINED the scope is reported added",
      d2["added"] == ["g3"] and d2["removed"] == [] and d2["drifted"])
check("  and described as unpriced work", "not contain" in d2["means"])
d3 = pk.drift(["g1", "g2"], ["g1"])
check("an element that LEFT the scope is reported removed",
      d3["removed"] == ["g2"] and d3["added"] == [])
check("  and described as a change the shop has not been told about",
      "no longer matches" in d3["means"])
d4 = pk.drift(["g1", "g2"], ["g1", "g3"])
check("both directions are reported separately, never netted to 'still 2 elements'",
      d4["added"] == ["g3"] and d4["removed"] == ["g2"] and d4["stable"] == 1)

# --- 4. which list is authoritative ---------------------------------------------------------------
def kit(**data):
    state = data.pop("state", "draft")
    return {"id": "k1", "ref": "KIT-001", "workflow_state": state,
            "data": {"name": "L3 duct kit", "trade": "MEP", **data}}


draft = pk.assess(kit(selector="IfcDuctSegment & storey=L3",
                      frozen_guids="g1\ng2\ng9"), IDX, today="2026-04-01")
check("before release the SELECTOR defines the kit", draft["scope_source"] == "selector")
check("  so it holds the 2 elements the selector matches, not the 3 frozen",
      draft["elements"] == 2, draft["elements"])
check("  and drift is not reported — there is nothing to drift from yet", draft["drift"] is None)

released = pk.assess(kit(state="released", selector="IfcDuctSegment & storey=L3",
                         frozen_guids="g1\ng2\ng9"), IDX, today="2026-04-01")
check("after release the FROZEN list defines the kit", released["scope_source"] == "frozen")
check("  so it holds 3 elements — including one the model no longer has",
      released["elements"] == 3)
check("  the missing one is reported unresolved", released["bom"]["unresolved"] == ["g9"])
codes = {b["code"] for b in released["blockers"]}
check("  and that is a blocker", "unresolved_elements" in codes, sorted(codes))
check("  as is the drift against the live selector", "scope_drift" in codes, sorted(codes))
check("  the kit is not ready", released["ready"] is False)

naked = pk.assess(kit(state="released", selector="IfcDuctSegment & storey=L3"), IDX,
                  today="2026-04-01")
check("a kit released with NOTHING frozen is called out specifically",
      "released_without_freezing" in {b["code"] for b in naked["blockers"]})

clean = pk.assess(kit(state="released", selector="IfcDuctSegment & storey=L3",
                      frozen_guids="g1\ng2"), IDX, today="2026-04-01")
check("a released kit whose frozen list still matches has no drift",
      clean["drift"]["drifted"] is False)

# --- 5. the schedule and delivery tie -------------------------------------------------------------
task = {"id": "t1", "ref": "PP-007", "workflow_state": "pulled",
        "data": {"task": "Hang L3 duct", "planned_week": "2026-W18",
                 "constraints": ["Materials", "Prerequisite work"]}}
free_task = {"id": "t2", "ref": "PP-008", "workflow_state": "made_ready",
             "data": {"task": "Hang L3 duct", "planned_week": "2026-W18", "constraints": []}}
late = {"id": "d1", "ref": "DEL-004", "data": {"date": "2026-04-20", "supplier": "Acme Sheet Metal"}}
ontime = {"id": "d2", "ref": "DEL-005", "data": {"date": "2026-04-05", "supplier": "Acme Sheet Metal"}}

k = kit(state="released", selector="IfcDuctSegment & storey=L3", frozen_guids="g1\ng2",
        needed_on_site="2026-04-10")
a = pk.assess(k, IDX, pull_task=task, delivery=late, today="2026-04-01")
codes = {b["code"] for b in a["blockers"]}
check("an open make-ready constraint on the installing task blocks the kit",
      "task_constrained" in codes, sorted(codes))
check("  and names the constraints", "Materials" in next(
    b["detail"] for b in a["blockers"] if b["code"] == "task_constrained"))
check("a delivery after the need-by date blocks it", "delivery_late" in codes)
check("  and says by how many days",
      "10 day(s) late" in next(b["detail"] for b in a["blockers"] if b["code"] == "delivery_late"))

ok = pk.assess(k, IDX, pull_task=free_task, delivery=ontime, today="2026-04-01")
check("with the constraints cleared and the delivery early, the kit is ready",
      ok["ready"] is True, ok["blockers"])

nolink = pk.assess(kit(state="released", selector="IfcDuctSegment & storey=L3",
                       frozen_guids="g1\ng2"), IDX, today="2026-04-01")
check("a kit with no pull task is blocked — nothing connects delivery to need",
      "no_pull_task" in {b["code"] for b in nolink["blockers"]})
passed = pk.assess(kit(state="released", selector="IfcDuctSegment & storey=L3",
                       frozen_guids="g1\ng2", needed_on_site="2026-03-01"), IDX,
                   pull_task=free_task, delivery=ontime, today="2026-04-01")
check("a passed need-by date on an uninstalled kit is a blocker",
      "need_by_passed" in {b["code"] for b in passed["blockers"]})
installed = pk.assess(kit(state="installed", selector="IfcDuctSegment & storey=L3",
                          frozen_guids="g1\ng2", needed_on_site="2026-03-01"), IDX,
                      pull_task=free_task, delivery=ontime, today="2026-04-01")
check("  but not once it is installed",
      "need_by_passed" not in {b["code"] for b in installed["blockers"]})

# --- 6. no model at all ----------------------------------------------------------------------------
nomodel = pk.assess(kit(selector="IfcDuctSegment"), None, today="2026-04-01")
check("with no model the kit still appears", nomodel["ref"] == "KIT-001")
check("  blocked, saying the scope cannot be resolved",
      "no_model" in {b["code"] for b in nomodel["blockers"]})

# --- 7. the register sorts by severity, not by date -------------------------------------------------
reg = pk.register(
    [
        {"id": "a", "ref": "KIT-A", "workflow_state": "released",
         "data": {"name": "late only", "selector": "IfcDuctSegment & storey=L3",
                  "frozen_guids": "g1\ng2", "needed_on_site": "2026-04-10",
                  "pull_task": "t2", "delivery": "d1"}},
        {"id": "b", "ref": "KIT-B", "workflow_state": "released",
         "data": {"name": "drifted", "selector": "IfcDuctSegment & storey=L3",
                  "frozen_guids": "g1", "needed_on_site": "2026-12-01",
                  "pull_task": "t2", "delivery": "d2"}},
    ],
    IDX, tasks_by_id={"t2": free_task}, deliveries_by_id={"d1": late, "d2": ontime},
    today="2026-04-01",
)
check("the register assesses every kit", reg["total"] == 2 and reg["blocked"] == 2)
check("the DRIFTED kit sorts above the merely late one — an unknown wrong beats a known problem",
      [k["ref"] for k in reg["kits"]] == ["KIT-B", "KIT-A"], [k["ref"] for k in reg["kits"]])
check("blocker counts are tallied", reg["blocker_counts"].get("scope_drift") == 1
      and reg["blocker_counts"].get("delivery_late") == 1, reg["blocker_counts"])
check("the register says whether a model was loaded at all", reg["model_loaded"] is True)

# --- 8. freeze refuses to write a scope that isn't one ---------------------------------------------
f = pk.freeze(kit(selector="IfcDuctSegment & storey=L3"), IDX)
check("freeze returns the resolved list", f["guids"] == ["g1", "g2"] or sorted(f["guids"]) == ["g1", "g2"])
check("  as newline-separated text for the record", f["frozen_guids"].count("\n") == 1)
for label, sel, idx_ in (("an empty selector", "", IDX),
                         ("a selector matching nothing", "IfcWall & storey=L9", IDX),
                         ("a broken selector", "&&&", IDX),
                         ("no model", "IfcDuctSegment", None)):
    try:
        pk.freeze(kit(selector=sel), idx_)
        check(f"freeze refuses {label}", False, "no exception")
    except ValueError:
        check(f"freeze refuses {label}", True)

# --- 9. parsing the frozen list ---------------------------------------------------------------------
check("the frozen list parses newlines and commas",
      pk.parse_guids("g1\ng2, g3\n\n g4 ") == ["g1", "g2", "g3", "g4"])
check("  dedupes while keeping the order somebody wrote",
      pk.parse_guids("g2\ng1\ng2") == ["g2", "g1"])
check("  and an empty field is an empty list", pk.parse_guids(None) == [])

print()
if FAILED:
    print(f"prefab_kit: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("prefab_kit: all checks passed")
