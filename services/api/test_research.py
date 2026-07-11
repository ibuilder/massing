"""Built-world techniques (R2 takt/LOB · R4 lean PPC · R5 benchmarks + comps).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_research.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_research.db"
os.environ["STORAGE_DIR"] = "./test_storage_research"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_research.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api import fourd, lean, takt  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- C3: 4D timeline engine (direct) — build order + cumulative progress -------
_plan = takt.plan(3)
_els = [
    {"guid": "g1", "ifc_class": "IfcColumn", "storey": "Level 1"},   # Structure, floor 0
    {"guid": "g2", "ifc_class": "IfcWall", "storey": "Level 1"},     # Envelope, floor 0
    {"guid": "g3", "ifc_class": "IfcColumn", "storey": "Level 3"},   # Structure, floor 2
    {"guid": "g4", "ifc_class": "IfcFurniture", "storey": "Level 3"},  # Finishes, floor 2
]
_tl = fourd.timeline(_plan, _els)
assert _tl["element_count"] == 4 and _tl["by_trade"]["Structure"] == 2, _tl["by_trade"]
# frames are day-ordered, cumulative is monotonic and ends at 100% / all elements
days = [f["day"] for f in _tl["frames"]]
assert days == sorted(days), days
assert _tl["frames"][-1]["completed_cumulative"] == 4 and _tl["frames"][-1]["pct"] == 100.0, _tl["frames"][-1]
# Structure on floor 0 completes before Structure on floor 2 (the train ascends)
_struct_days = sorted(f["day"] for f in _tl["frames"] for g in f["new_guids"] if g in ("g1", "g3"))
assert _struct_days[0] < _struct_days[-1], _struct_days
# an unknown storey defaults to ground; empty input is safe
assert fourd._floor_index("Level 2") == 1 and fourd._floor_index(None) == 0
assert fourd.timeline(_plan, [])["element_count"] == 0

# --- relational 4D: the GC schedule (schedule_activity) drives the model -------
# (A) an activity that hard-tags a GUID sets that element's exact finish date;
# (B) untagged elements fall back to their trade's activities by floor.
_acts = [
    {"name": "Structure L1", "trade": "Structure", "start": "2026-01-05", "finish": "2026-01-20",
     "element_guids": ["g1"]},                                   # hard-tags g1
    {"name": "Structure L3", "trade": "Structure", "start": "2026-02-01", "finish": "2026-02-20"},
    {"name": "Envelope",     "trade": "Envelope",  "start": "2026-03-01", "finish": "2026-03-15"},
    {"name": "Finishes",     "trade": "Finishes",  "start": "2026-04-01", "finish": "2026-04-30"},
]
_g = fourd.timeline_from_activities(_acts, _els)
assert _g["source"] == "gc" and _g["element_count"] == 4, _g
assert _g["linked"] == 1 and _g["unlinked"] == 3, (_g["linked"], _g["unlinked"])  # only g1 hard-tied
# frames carry real calendar dates, ordered, ending at 100%
assert all("date" in f for f in _g["frames"]) and _g["frames"][-1]["pct"] == 100.0, _g["frames"][-1]
# g1 finishes on its activity's exact date; g2 (Envelope, floor 0) on the Envelope activity
_when = {g: f["date"] for f in _g["frames"] for g in f["new_guids"]}
assert _when["g1"] == "2026-01-20", _when
assert _when["g2"] == "2026-03-15", _when      # Envelope trade activity finish
assert _when["g4"] == "2026-04-30", _when      # Finishes trade activity finish
# Structure floor-0 (g1) completes before Structure floor-2 (g3) — the schedule ascends
assert _when["g1"] < _when["g3"], _when
# no activities with finish dates → empty (caller falls back to takt)
assert fourd.timeline_from_activities([{"name": "x"}], _els)["element_count"] == 0

# --- R2: takt / line-of-balance ----------------------------------------------
p = takt.plan(10)                                  # 10 floors, default 5-trade train
assert len(p["trades"]) == 5 and p["floors"] == 10
# each trade ascends floor by floor; finish is monotonic and after start
struct = p["trades"][0]
assert struct["floor_starts"] == sorted(struct["floor_starts"]), "trade ascends in order"
# later trades finish after earlier ones (the train chases up the building)
assert p["trades"][-1]["finish_day"] > p["trades"][0]["finish_day"], "finishes chase upward"
assert p["duration_days"] > 0 and p["crew_peak"] == 5 and p["floors_per_week"] > 0, p
# JIT: every floor×trade has a delivery, ordered by need date
assert len(p["delivery_plan"]) == 10 * 5 and p["delivery_plan"] == sorted(p["delivery_plan"], key=lambda d: d["deliver_by_day"])
# more floors -> longer duration
assert takt.plan(20)["duration_days"] > p["duration_days"]
# faster takt -> faster ascent
fast = takt.plan(10, [{"name": "Structure", "takt_days": 2}])
assert fast["floors_per_week"] > p["floors_per_week"]

# --- C3: 4D sequencing — elements appear when their trade reaches their floor -
from aec_api import fourd  # noqa: E402
els = [{"guid": "c1", "ifc_class": "IfcColumn", "storey": "Level 1"},
       {"guid": "c2", "ifc_class": "IfcColumn", "storey": "Level 3"},
       {"guid": "w1", "ifc_class": "IfcWall", "storey": "Level 1"},
       {"guid": "s1", "ifc_class": "IfcSpace", "storey": "Level 1"}]
tl = fourd.timeline(takt.plan(3), els)
assert tl["element_count"] == 4 and tl["frames"], tl
# cumulative is monotonic and ends at 100%
assert tl["frames"][-1]["completed_cumulative"] == 4 and tl["frames"][-1]["pct"] == 100.0, tl["frames"][-1]
# structure (column L1) completes before interiors (space L1) — trades chase in order
col_day = min(f["day"] for f in tl["frames"] if "c1" in f["new_guids"])
space_day = min(f["day"] for f in tl["frames"] if "s1" in f["new_guids"])
assert col_day < space_day, (col_day, space_day)
# a higher floor's column finishes after the ground floor's
c2_day = min(f["day"] for f in tl["frames"] if "c2" in f["new_guids"])
assert c2_day > col_day, (c2_day, col_day)

# --- R4: lean PPC ------------------------------------------------------------
recs = [{"data": {"status": "Complete"}}, {"data": {"status": "Complete"}},
        {"data": {"status": "Complete"}}, {"data": {"status": "Complete"}},
        {"data": {"status": "Missed", "variance_reason": "Materials"}}]
m = lean.ppc(recs)
assert m["commitments"] == 5 and m["completed"] == 4 and m["ppc"] == 0.8, m
assert m["rating"] == "good" and m["top_variance_reasons"][0]["reason"] == "Materials", m
assert lean.ppc([])["ppc"] == 0.0

# --- endpoints + R5 ----------------------------------------------------------
with TestClient(app) as c:
    t = c.post("/schedule/takt", json={"floors": 8})
    assert t.status_code == 200 and t.json()["crew_peak"] == 5, t.text
    svg = c.get("/schedule/takt.svg", params={"floors": 8})
    assert svg.status_code == 200 and svg.content[:4] == b"<svg" and b"floors/wk" in svg.content, svg.status_code
    b = c.get("/benchmarks")
    assert b.status_code == 200 and "cap_rate" in b.json()["benchmarks"], b.text
    pid = c.post("/projects", json={"name": "Lean Job"}).json()["id"]
    # seed weekly-plan commitments via the auto-created module, then read PPC
    for st in ("Complete", "Complete", "Missed"):
        body = {"data": {"task": "Pour deck", "status": st, "variance_reason": "Labor"}}
        c.post(f"/projects/{pid}/modules/weekly_plan", json=body)
    r = c.get(f"/projects/{pid}/lean/ppc")
    assert r.status_code == 200 and r.json()["commitments"] == 3 and abs(r.json()["ppc"] - 0.667) < 0.01, r.text
    # comparables module auto-created
    cmp = c.post(f"/projects/{pid}/modules/comparable", json={"data": {"address": "123 Main", "cap_rate": 5.5}})
    assert cmp.status_code in (200, 201), cmp.text
    # 4D endpoint responds even with no published model (empty timeline)
    fd = c.get(f"/projects/{pid}/schedule/4d")
    assert fd.status_code == 200 and "frames" in fd.json() and "duration_days" in fd.json(), fd.text
    assert fd.json()["source"] == "takt", fd.json().get("source")
    # Primavera P6 .xer import → 4D reports real calendar dates (source=p6); bad file → 422; clear → takt
    _xer = "\n".join(["\t".join(["%T", "TASK"]),
        "\t".join(["%F", "task_code", "task_name", "target_start_date", "target_end_date"]),
        "\t".join(["%R", "A1010", "Foundations", "2026-03-01 08:00", "2026-03-20 17:00"]),
        "\t".join(["%R", "A1020", "Superstructure", "2026-03-21 08:00", "2026-07-15 17:00"])])
    imp = c.post(f"/projects/{pid}/schedule/import-xer", files={"file": ("p.xer", _xer, "application/octet-stream")})
    assert imp.status_code == 201 and imp.json()["count"] == 2 and imp.json()["start"] == "2026-03-01", imp.text
    # imported tasks are now EDITABLE schedule_activity records (the GC can keep updating them)
    assert imp.json()["created"] == 2 and imp.json()["updated"] == 0, imp.json()
    acts = c.get(f"/projects/{pid}/modules/schedule_activity").json()
    assert len(acts) == 2 and {a["data"]["wbs"] for a in acts} == {"A1010", "A1020"}, acts
    # bare import (no trades yet) keeps the takt+P6 sequence for the 4D scrub (real calendar window)
    fd2 = c.get(f"/projects/{pid}/schedule/4d").json()
    assert fd2["source"] == "p6" and fd2["start_date"] == "2026-03-01" and fd2["finish_date"] == "2026-07-15", fd2
    # the GC edits an imported activity (assign a trade) — once trades exist the 4D switches to gc
    fnd = next(a for a in acts if a["data"]["wbs"] == "A1010")
    c.patch(f"/projects/{pid}/modules/schedule_activity/{fnd['id']}", json={"trade": "Structure", "percent": 50})
    assert c.get(f"/projects/{pid}/modules/schedule_activity/{fnd['id']}").json()["data"]["trade"] == "Structure"
    assert c.get(f"/projects/{pid}/schedule/4d").json()["source"] == "gc"
    # the GC also adds their own task; re-import updates the imported pair in place (no duplicates) and
    # MERGES — preserving the GC's trade edit — while the GC-added task is untouched
    c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": {"name": "GC-added inspection", "trade": "MEP"}})
    imp2 = c.post(f"/projects/{pid}/schedule/import-xer", files={"file": ("p.xer", _xer, "application/octet-stream")})
    assert imp2.json()["updated"] == 2 and imp2.json()["created"] == 0, imp2.json()
    assert len(c.get(f"/projects/{pid}/modules/schedule_activity").json()) == 3, "2 imported (updated) + 1 GC-added"
    assert c.get(f"/projects/{pid}/modules/schedule_activity/{fnd['id']}").json()["data"]["trade"] == "Structure", "re-import preserved GC edit"
    assert c.post(f"/projects/{pid}/schedule/import-xer", files={"file": ("x.xer", "junk", "text/plain")}).status_code == 422
    cl = c.delete(f"/projects/{pid}/schedule/import-xer").json()
    assert cl["removed_activities"] == 2, cl              # clears only the imported tasks
    left = c.get(f"/projects/{pid}/modules/schedule_activity").json()
    assert len(left) == 1 and left[0]["data"]["name"] == "GC-added inspection", left   # GC's task survives
    c.delete(f"/projects/{pid}/modules/schedule_activity/{left[0]['id']}")
    assert c.get(f"/projects/{pid}/schedule/4d").json()["source"] == "takt"

    # the SAME endpoint auto-detects Primavera P6 **XML (PMXML)** and creates the same activity records
    _pmxml = ("<APIBusinessObjects><Project>"
              "<Activity><Id>X1</Id><Name>Sitework</Name>"
              "<PlannedStartDate>2026-03-01T08:00:00</PlannedStartDate>"
              "<PlannedFinishDate>2026-03-10T17:00:00</PlannedFinishDate></Activity>"
              "<Activity><Id>X2</Id><Name>Utilities</Name>"
              "<PlannedStartDate>2026-03-11T08:00:00</PlannedStartDate>"
              "<PlannedFinishDate>2026-03-20T17:00:00</PlannedFinishDate></Activity>"
              "</Project></APIBusinessObjects>")
    impx = c.post(f"/projects/{pid}/schedule/import-xer", files={"file": ("p.xml", _pmxml, "application/xml")})
    assert impx.status_code == 201 and impx.json()["count"] == 2, impx.text
    xacts = c.get(f"/projects/{pid}/modules/schedule_activity").json()
    assert {a["data"]["name"] for a in xacts} == {"Sitework", "Utilities"}, xacts
    c.delete(f"/projects/{pid}/schedule/import-xer")       # restore the clean slate for the block below
    assert len(c.get(f"/projects/{pid}/modules/schedule_activity").json()) == 0

    # relational: once GC schedule_activity records exist, the 4D scrub is driven by them (source=gc),
    # the SAME activities behind the Gantt / Line-of-Balance / CPM views — one relational schedule.
    for a in [{"name": "Foundations", "trade": "Structure", "start": "2026-03-01", "finish": "2026-03-20"},
              {"name": "Superstructure", "trade": "Structure", "start": "2026-03-21", "finish": "2026-07-15"}]:
        c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": a})
    gcfd = c.get(f"/projects/{pid}/schedule/4d").json()
    assert gcfd["source"] == "gc" and gcfd["activity_count"] == 2, gcfd
    # the same activities also render the Gantt + Line-of-Balance SVGs and the CPM analysis
    assert c.get(f"/projects/{pid}/schedule/gantt.svg").headers["content-type"].startswith("image/svg")
    assert c.get(f"/projects/{pid}/schedule/lob.svg").headers["content-type"].startswith("image/svg")
    cpm = c.get(f"/projects/{pid}/schedule/cpm").json()
    assert cpm.get("activities") or cpm.get("critical_path") is not None, cpm
    # ?source=takt still forces the generated takt sequence (escape hatch)
    assert c.get(f"/projects/{pid}/schedule/4d?source=takt").json()["source"] == "takt"

    # lookahead + milestone schedules (the field's short-interval plan + the key dates)
    from datetime import date as _date, timedelta as _td
    t0 = _date.today()
    started = (t0 - _td(days=2)).isoformat(); soon = (t0 + _td(days=10)).isoformat()
    far = (t0 + _td(days=90)).isoformat(); past = (t0 - _td(days=5)).isoformat()
    c.post(f"/projects/{pid}/modules/schedule_activity",
           json={"data": {"name": "Pour slab L2", "trade": "Concrete", "start": started, "finish": soon, "percent": 25}})
    c.post(f"/projects/{pid}/modules/schedule_activity",
           json={"data": {"name": "TCO", "activity_type": "Milestone", "start": soon, "finish": soon}})
    c.post(f"/projects/{pid}/modules/schedule_activity",
           json={"data": {"name": "Topping out", "activity_type": "Milestone", "start": far, "finish": far}})
    c.post(f"/projects/{pid}/modules/schedule_activity",
           json={"data": {"name": "Permit (late)", "activity_type": "Milestone", "start": past, "finish": past}})
    la = c.get(f"/projects/{pid}/schedule/lookahead?weeks=3").json()
    assert la["weeks"] == 3 and la["count"] >= 1, la
    assert any(a["name"] == "Pour slab L2" and a["status"] == "in_progress"
               for wk in la["weeks_detail"] for a in wk["activities"]), la       # near-term task shows
    assert not any(a["name"] == "Topping out" for wk in la["weeks_detail"] for a in wk["activities"]), "far milestone out of window"
    ms = c.get(f"/projects/{pid}/schedule/milestones").json()
    names = {m["name"]: m["status"] for m in ms["milestones"]}
    assert names.get("TCO") == "due_soon" and names.get("Topping out") == "upcoming", names
    assert names.get("Permit (late)") == "late", names
    assert "Pour slab L2" not in names, "non-milestone task excluded from milestone schedule"
    assert ms["milestones"] == sorted(ms["milestones"], key=lambda x: x["date"]), "milestones date-sorted"

    # earned value: BAC/EV/PV/SPI over activities that carry a budgeted cost
    done = (t0 - _td(days=20)).isoformat(); midend = (t0 - _td(days=10)).isoformat()
    midstart = (t0 - _td(days=10)).isoformat(); future = (t0 + _td(days=10)).isoformat()
    c.post(f"/projects/{pid}/modules/schedule_activity",
           json={"data": {"name": "Foundation EV", "budget": 50000, "percent": 100, "start": done, "finish": midend}})
    c.post(f"/projects/{pid}/modules/schedule_activity",
           json={"data": {"name": "Frame EV", "budget": 50000, "percent": 20, "start": midstart, "finish": future}})
    ev = c.get(f"/projects/{pid}/schedule/earned-value").json()
    assert ev["bac"] == 100000 and ev["ev"] == 60000 and ev["pv"] == 75000, ev   # 50k done + 10k of frame; PV 50k+25k
    assert ev["spi"] == 0.8 and ev["status"] == "behind", ev                     # EV/PV = 0.8 → behind schedule
    assert ev["sv"] == -15000 and ev["activity_count"] == 2, ev                  # only the two budgeted activities
    assert ev["activities"][0]["name"] == "Frame EV", ev["activities"]           # worst variance first

    # baseline + variance: snapshot the plan, then measure slip against it
    assert c.get(f"/projects/{pid}/schedule/variance").status_code == 409        # no baseline yet
    a = c.post(f"/projects/{pid}/modules/schedule_activity",
               json={"data": {"name": "BL-A", "start": "2026-05-01", "finish": "2026-05-20"}}).json()
    bl = c.post(f"/projects/{pid}/schedule/baseline").json()
    assert bl["count"] >= 1, bl
    var0 = c.get(f"/projects/{pid}/schedule/variance").json()
    assert any(x["name"] == "BL-A" and x["status"] == "on_baseline" for x in var0["activities"]), var0
    # slip BL-A's finish by 6 days, and add a new activity after the baseline
    c.patch(f"/projects/{pid}/modules/schedule_activity/{a['id']}", json={"finish": "2026-05-26"})
    c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": {"name": "BL-late-add", "start": "2026-06-01", "finish": "2026-06-10"}})
    var = c.get(f"/projects/{pid}/schedule/variance").json()
    bla = next(x for x in var["activities"] if x["name"] == "BL-A")
    assert bla["finish_var"] == 6 and bla["status"] == "slipped", bla
    assert any(x["name"] == "BL-late-add" and x["status"] == "added" for x in var["activities"]), var
    assert var["summary"]["slipped"] >= 1 and var["summary"]["max_slip_days"] >= 6, var["summary"]
    assert var["activities"][0]["finish_var"] is not None, "biggest slip sorted first"

print(f"RESEARCH OK - takt {p['duration_days']}d / {p['floors_per_week']} fl-wk / {len(p['delivery_plan'])} JIT deliveries; "
      f"lean PPC {m['ppc']} ({m['rating']}); benchmarks + weekly_plan + comparable modules + endpoints verified")
