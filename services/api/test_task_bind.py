"""R25-TASK-BIND — the 4D binding written INTO the model, and read back out unchanged.

`cost_ifc` did this for money (v0.3.684): a priced element carries its price in the file. This is the
time half, and the asymmetry it closes is the interesting part. `schedule.from_ifc` could always
*read* `IfcTask` and its outputs — but nothing in the platform could *write* them, so a schedule
authored elsewhere could be consumed while the platform's own schedule lived only in its database:
unable to travel with the file, invisible to every other tool, and re-derived on each export. A read
half with no write half is not a partial feature; it is a one-way door.

The native link is `IfcRelAssignsToProduct` — the task's **output**. The first version of this wrote
`IfcRelAssignsToProcess`, which is the task's *input* relation ("this task operates on that product").
Both are real IFC and both round-trip cleanly through a reader written to match, so the mistake is
invisible to any test that only checks its own writer. What caught it was asserting the binding
against this repo's **pre-existing** reader, which — like every tool that asks "what does this task
build" — reads outputs. That assertion is the most valuable line in this file.

The alternative to either — a bespoke task↔element join table — would put the 4D spine *outside* the
model, which is the decision the 5D research already forced once.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_task_bind.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_task_bind.db"
os.environ["STORAGE_DIR"] = "./test_storage_task_bind"
if os.path.exists("./test_task_bind.db"):
    os.remove("./test_task_bind.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell  # noqa: E402

from aec_data import fourd_ifc, schedule  # noqa: E402


def model_with(n: int):
    m = ifcopenshell.file(schema="IFC4")
    m.create_entity("IfcOwnerHistory")
    walls = [m.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name=f"Wall {i}")
             for i in range(n)]
    return m, walls


# ---- the round trip, in BOTH directions ------------------------------------------------------------
m, walls = model_with(4)
g = [w.GlobalId for w in walls]

res = fourd_ifc.write_work_schedule(m, [
    {"id": "A-100", "name": "Erect L1 walls", "start": "2026-08-03", "finish": "2026-08-14",
     "guids": [g[0], g[1]]},
    {"id": "A-110", "name": "Erect L2 walls", "start": "2026-08-17", "finish": "2026-08-28",
     "guids": [g[2]], "task_type": "INSTALLATION"},
])
assert res["written"] == 2 and not res["missing_guids"], res
assert res["schedule"].is_a("IfcWorkSchedule")

back = {t["id"]: t for t in fourd_ifc.read_work_schedule(m)}
assert set(back) == {"A-100", "A-110"}, back
assert back["A-100"]["guids"] == sorted([g[0], g[1]]), back["A-100"]
assert back["A-110"]["guids"] == [g[2]]
assert back["A-110"]["task_type"] == "INSTALLATION"
assert back["A-100"]["task_type"] == "CONSTRUCTION", "the default is stated, not NOTDEFINED"
assert back["A-100"]["start"].startswith("2026-08-03")
assert back["A-100"]["finish"].startswith("2026-08-14")

# ...and the SAME binding is visible to the pre-existing reader, which never knew about this writer.
# That is the whole claim: the schedule is in the model, not in our database with a view over it.
via_schedule = {a["id"]: a for a in schedule.from_ifc(m)}
assert set(via_schedule) == {"A-100", "A-110"}, via_schedule
assert sorted(via_schedule["A-100"]["guids"]) == sorted([g[0], g[1]]), via_schedule["A-100"]

# ---- an element the model does not contain is REPORTED, and its task is still written -------------
# The work is real. Dropping the task would make a programme quietly shorter than the project, and the
# caller would learn about it from a missed date rather than from a report.
m2, walls2 = model_with(1)
res2 = fourd_ifc.write_work_schedule(m2, [
    {"id": "A-200", "name": "Pour slab", "start": "2026-09-01", "finish": "2026-09-05",
     "guids": [walls2[0].GlobalId, "0notinthemodel00000000"]},
])
assert res2["written"] == 1, res2
assert res2["missing_guids"] == ["0notinthemodel00000000"], res2
assert fourd_ifc.read_work_schedule(m2)[0]["guids"] == [walls2[0].GlobalId]

# a task whose guids match NOTHING is still a task
m3, _ = model_with(0)
res3 = fourd_ifc.write_work_schedule(m3, [
    {"id": "A-300", "name": "Mobilise", "start": "2026-07-01", "finish": "2026-07-03",
     "guids": ["1nope", "2nope"]}])
assert res3["written"] == 1 and len(res3["missing_guids"]) == 2, res3
assert fourd_ifc.read_work_schedule(m3)[0]["guids"] == [], "no binding, but the task survives"

# ---- HALF a date range is not a date range --------------------------------------------------------
# Writing one end would let every downstream duration and float read as authoritative while resting on
# a date nobody supplied. No TaskTime at all, and the task is named in `partial_dates`.
m4, walls4 = model_with(1)
res4 = fourd_ifc.write_work_schedule(m4, [
    {"id": "A-400", "name": "Open-ended", "start": "2026-08-03", "finish": "",
     "guids": [walls4[0].GlobalId]},
    {"id": "A-410", "name": "Unreadable finish", "start": "2026-08-03", "finish": "next tuesday",
     "guids": []},
    {"id": "A-420", "name": "No dates at all", "guids": []},
])
r4 = {t["id"]: t for t in fourd_ifc.read_work_schedule(m4)}
assert r4["A-400"]["start"] is None and r4["A-400"]["finish"] is None, r4["A-400"]
assert r4["A-410"]["start"] is None, r4["A-410"]
assert res4["partial_dates"] == ["A-400", "A-410"], res4
# a task with NO dates is not "partial" — nobody attempted a range, so nothing was dropped
assert "A-420" not in res4["partial_dates"], res4
# and the binding still happened: a dateless task is unscheduled, not unbound
assert r4["A-400"]["guids"] == [walls4[0].GlobalId]

# ---- ABSENT defaults; EMPTY is refused -------------------------------------------------------------
# Most tasks on a building programme build something, so an absent type defaults to CONSTRUCTION and
# making every caller repeat it adds no information. An EMPTY one is somebody who tried to state a
# type and failed — writing CONSTRUCTION over that puts a confident wrong label in the file. Same
# distinction cost_ifc draws for `basis`, and the code originally got it wrong in this direction.
m5a, _ = model_with(0)
fourd_ifc.write_work_schedule(m5a, [{"id": "D", "name": "Defaulted", "guids": []}])
assert fourd_ifc.read_work_schedule(m5a)[0]["task_type"] == "CONSTRUCTION"

# A mislabelled task type is invisible in the file and wrong in every downstream filter.
m5, _ = model_with(0)
for bad in ("BUILDING", "", "  ", "construction!"):
    try:
        fourd_ifc.write_work_schedule(m5, [{"id": "X", "name": "X", "task_type": bad, "guids": []}])
        raise AssertionError(f"accepted task_type {bad!r}")
    except ValueError:
        pass
# A REJECTED WRITE LEAVES THE MODEL AS IT FOUND IT. `model` belongs to the caller, so raising
# part-way through left an IfcWorkSchedule with no assignment relationship and orphan IfcTasks
# belonging to no schedule — and a caller following this repo's convention of turning ValueError into
# a 422 would then save that model. Validation runs over the whole batch before anything is created.
m5b, w5b = model_with(1)
before_ids = {e.id() for e in m5b.by_type("IfcRoot")}
try:
    fourd_ifc.write_work_schedule(m5b, [
        {"id": "GOOD", "name": "Fine", "guids": [w5b[0].GlobalId]},
        {"id": "BAD", "name": "Bad type", "task_type": "NOPE", "guids": []},
    ])
    raise AssertionError("accepted a batch containing an invalid task_type")
except ValueError:
    pass
assert {e.id() for e in m5b.by_type("IfcRoot")} == before_ids, "a refused write must create nothing"
assert not m5b.by_type("IfcWorkSchedule"), m5b.by_type("IfcWorkSchedule")
assert not m5b.by_type("IfcTask"), m5b.by_type("IfcTask")
assert fourd_ifc.read_work_schedule(m5b) == []

# ...but the canonical values are accepted, in any case
m6, _ = model_with(0)
fourd_ifc.write_work_schedule(m6, [{"id": "X", "name": "X", "task_type": "demolition", "guids": []}])
assert fourd_ifc.read_work_schedule(m6)[0]["task_type"] == "DEMOLITION"

# ---- read/write SYMMETRY, asserted as a property --------------------------------------------------
# Two functions encoding one format WILL drift. Every field the writer accepts must survive the round
# trip, and this is checked field-by-field rather than by spot-checking one task.
m7, walls7 = model_with(3)
src = [{"id": f"A-{i}", "name": f"Task {i}", "task_type": "CONSTRUCTION",
        "start": f"2026-08-{10 + i:02d}", "finish": f"2026-08-{20 + i:02d}",
        "guids": [walls7[i].GlobalId]} for i in range(3)]
fourd_ifc.write_work_schedule(m7, src)
got = {t["id"]: t for t in fourd_ifc.read_work_schedule(m7)}
assert set(got) == {t["id"] for t in src}, (set(got), {t["id"] for t in src})
for t in src:
    r = got[t["id"]]
    assert r["name"] == t["name"], (r, t)
    assert r["task_type"] == t["task_type"], (r, t)
    assert r["start"].startswith(t["start"]), (r, t)
    assert r["finish"].startswith(t["finish"]), (r, t)
    assert r["guids"] == t["guids"], (r, t)

# an empty programme writes a schedule and no tasks — and reads back as no tasks, not as an error
m8, _ = model_with(0)
res8 = fourd_ifc.write_work_schedule(m8, [])
assert res8["written"] == 0 and fourd_ifc.read_work_schedule(m8) == []

# ---- REVIEW FIX: a REJECTED write leaves the model exactly as it found it -------------------------
# task_type was validated INSIDE the write loop, after the IfcWorkSchedule and the earlier IfcTasks
# had already been created -- so a ValueError left an orphaned schedule carrying no
# IfcRelAssignsToControl plus tasks belonging to no schedule. `model` is the caller's, and this repo's
# convention is to turn ValueError into a 422, after which the caller may well go on to save it.
m10, walls10 = model_with(3)
g10 = [w.GlobalId for w in walls10]
try:
    fourd_ifc.write_work_schedule(m10, [
        {"id": "R-1", "name": "fine", "start": "2026-09-01", "finish": "2026-09-04",
         "guids": [g10[0]]},
        {"id": "R-2", "name": "bad type", "task_type": "NOT_A_REAL_TYPE", "guids": [g10[1]]},
    ])
    raise AssertionError("an unrecognised task_type must be refused")
except ValueError:
    pass
assert m10.by_type("IfcTask") == [], "a refused write must not leave tasks behind"
assert m10.by_type("IfcWorkSchedule") == [], "nor an orphaned schedule"
assert m10.by_type("IfcRelAssignsToProduct") == [], "nor dangling 4D bindings"

# ---- REVIEW FIX: the MAX_TASKS cap is stated, never silent ----------------------------------------
# This module argues that dropping work "would make a programme quietly shorter than the project" --
# and `tasks[:MAX_TASKS]` then did exactly that, with nothing in the return saying so. A caller could
# only notice by comparing `written` against its own input length. `qto.measure` reports
# `geometry_capped` and `estimate_diff` reports `truncated` for the same reason.
m11, _ = model_with(1)
_over = fourd_ifc.MAX_TASKS + 7
r11 = fourd_ifc.write_work_schedule(m11, [{"id": f"T{i}"} for i in range(_over)])
assert r11["written"] == fourd_ifc.MAX_TASKS, r11["written"]
assert r11["truncated"] == 7, r11["truncated"]
m12, _ = model_with(1)
assert fourd_ifc.write_work_schedule(m12, [{"id": "T1"}])["truncated"] == 0, "no cap, no alarm"

# ---- REVIEW FIX: two schedules in one model stay TOLD APART ---------------------------------------
# The writer groups tasks under a named IfcWorkSchedule via IfcRelAssignsToControl; the reader ignored
# that relation entirely, so a model holding a baseline AND a current programme -- the ordinary case,
# the platform has schedule baselines -- read back as one flat list with the two interleaved and no
# way to separate them. A reader that discards the grouping its own writer created is the one-way door
# this module exists to close.
m13, walls13 = model_with(2)
g13 = [w.GlobalId for w in walls13]
fourd_ifc.write_work_schedule(m13, [{"id": "B-1", "name": "base", "start": "2026-01-05",
                                     "finish": "2026-01-09", "guids": [g13[0]]}], name="Baseline")
fourd_ifc.write_work_schedule(m13, [{"id": "C-1", "name": "curr", "start": "2026-02-02",
                                     "finish": "2026-02-06", "guids": [g13[1]]}], name="Current")
back13 = {t["id"]: t for t in fourd_ifc.read_work_schedule(m13)}
assert set(back13) == {"B-1", "C-1"}, back13
assert back13["B-1"]["schedule"] == "Baseline", back13["B-1"]
assert back13["C-1"]["schedule"] == "Current", back13["C-1"]
assert back13["B-1"]["schedule_id"] != back13["C-1"]["schedule_id"], "distinct schedule GlobalIds"
# a task written by another tool with no schedule grouping is still reported, not hidden
m14, _ = model_with(1)
m14.create_entity("IfcTask", GlobalId=ifcopenshell.guid.new(), Identification="FOREIGN", Name="ext")
_loose = [t for t in fourd_ifc.read_work_schedule(m14) if t["id"] == "FOREIGN"]
assert len(_loose) == 1 and _loose[0]["schedule"] is None, _loose

print("R25-TASK-BIND OK - the 4D binding is now written INTO the model rather than held beside it. "
      "The asymmetry this closes is the point: schedule.from_ifc could always READ IfcTask and its "
      "outputs, but nothing could WRITE them, so a schedule authored in another tool could be "
      "consumed while the platform's own lived only in its database - unable to travel with the file, "
      "invisible to every other tool, re-derived on each export. A read half with no write half is not "
      "a partial feature, it is a one-way door. The native link is IfcRelAssignsToProduct - the "
      "task's OUTPUT - and the first version of this wrote IfcRelAssignsToProcess, the task's INPUT "
      "relation. Both are real IFC and both round-trip cleanly through a reader written to match, so "
      "the error is invisible to any test that only checks its own writer; what caught it was "
      "asserting against the PRE-EXISTING reader, which like every tool asking 'what does this task "
      "build' reads outputs. A bespoke join table would have put the 4D spine OUTSIDE the model, the "
      "decision the 5D research already forced once. Three behaviours "
      "are deliberate: a task whose GlobalIds are absent is still written and the ids REPORTED, "
      "because the work is real and dropping it makes a programme quietly shorter than the project; "
      "HALF a date range writes no dates at all, because a duration computed from one supplied end "
      "reads as authoritative while resting on a date nobody gave; and an unrecognised task type is "
      "REFUSED rather than written as NOTDEFINED, since a mislabelled task is invisible in the file "
      "and wrong in every downstream filter. Symmetry is asserted field-by-field in both directions - "
      "two functions encoding one format drift - and the binding is proved visible to the PRE-EXISTING "
      "reader, which is the whole claim: the schedule is in the model, not in a view over our database.")
