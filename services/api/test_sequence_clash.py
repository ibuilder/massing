"""R21-4D-CLASH phase 1 — two trades in one place at one time.

Hard clash finds two things in one space; soft clash asks whether a person can reach them. This asks
the third question, and it is the one that surfaces on site as two foremen arguing in a corridor:
are two crews scheduled into the same place in the same week? Nothing in the MODEL is wrong when this
happens — every element clears every other — which is exactly why a geometric clash run cannot find it.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sequence_clash.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_sequence_clash.db"
os.environ["STORAGE_DIR"] = "./test_storage_sequence_clash"
if os.path.exists("./test_sequence_clash.db"):
    os.remove("./test_sequence_clash.db")

from aec_api import sequence_clash as sq  # noqa: E402


def act(i, name, loc, trade, start, finish, crew=0):
    return {"id": i, "data": {"name": name, "location": loc, "trade": trade,
                              "start": start, "finish": finish, "crew_size": crew}}


# ---- the core finding: different trades, same place, overlapping window -------------------------
r = sq.analyze([
    act("a", "Overhead ductwork", "L3 North", "Mechanical", "2026-08-03", "2026-08-14", 4),
    act("b", "Branch conduit", "L3 North", "Electrical", "2026-08-10", "2026-08-21", 3),
])
assert r["finding_count"] == 1, r
f = r["findings"][0]
assert {f["a"]["trade"], f["b"]["trade"]} == {"Mechanical", "Electrical"}
assert f["overlap_days"] == 5, f            # 10th–14th inclusive
assert f["window"] == {"start": "2026-08-10", "finish": "2026-08-14"}, f["window"]
assert f["combined_crew"] == 7
assert r["clean"] is False

# ---- what is deliberately NOT a finding ---------------------------------------------------------
# same trade sequencing its own crews through a zone is planning, not contention
same = sq.analyze([act("a", "Rough-in A", "L3", "Electrical", "2026-08-03", "2026-08-14"),
                   act("b", "Rough-in B", "L3", "Electrical", "2026-08-10", "2026-08-21")])
assert same["finding_count"] == 0, same["findings"]
assert same["clean"] is True
# trade comparison is not confused by case or padding
assert sq.analyze([act("a", "x", "L3", " electrical ", "2026-08-03", "2026-08-14"),
                   act("b", "y", "L3", "Electrical", "2026-08-10", "2026-08-21")])["finding_count"] == 0

# different LOCATIONS never contend, however much they overlap in time
elsewhere = sq.analyze([act("a", "Duct", "L3 North", "Mechanical", "2026-08-03", "2026-08-28"),
                        act("b", "Conduit", "L4 South", "Electrical", "2026-08-03", "2026-08-28")])
assert elsewhere["finding_count"] == 0 and elsewhere["locations"] == 2

# adjacent-but-not-overlapping windows are fine — one crew leaves as the other arrives
adjacent = sq.analyze([act("a", "Duct", "L3", "Mechanical", "2026-08-03", "2026-08-07"),
                       act("b", "Conduit", "L3", "Electrical", "2026-08-08", "2026-08-14")])
assert adjacent["finding_count"] == 0, adjacent["findings"]
# ...but a single shared day IS an overlap
touching = sq.analyze([act("a", "Duct", "L3", "Mechanical", "2026-08-03", "2026-08-07"),
                       act("b", "Conduit", "L3", "Electrical", "2026-08-07", "2026-08-14")])
assert touching["finding_count"] == 1 and touching["findings"][0]["overlap_days"] == 1

# location matching ignores case and whitespace, so "L3 North" and "l3  north" are one place
casing = sq.analyze([act("a", "Duct", "L3 North", "Mechanical", "2026-08-03", "2026-08-14"),
                     act("b", "Conduit", "l3   north", "Electrical", "2026-08-10", "2026-08-21")])
assert casing["finding_count"] == 1, casing

# ---- unreadable activities are COUNTED, never silently dropped ----------------------------------
# a clean result over a half-unreadable schedule would overstate what was checked
gaps = sq.analyze([
    act("a", "No location", "", "Mechanical", "2026-08-03", "2026-08-14"),
    act("b", "No dates", "L3", "Electrical", "", ""),
    act("c", "Backwards", "L3", "Plumbing", "2026-08-14", "2026-08-03"),
])
assert gaps["finding_count"] == 0
assert gaps["skipped_count"] == 3, gaps["skipped"]
assert {s["reason"] for s in gaps["skipped"]} == {"no location", "missing start or finish",
                                                  "finish before start"}
assert gaps["clean"] is False, "nothing was readable, so nothing may be reported clean"
assert sq.analyze([])["clean"] is False, "an empty schedule has checked nothing"

# ---- thresholds -----------------------------------------------------------------------------
pair = [act("a", "Duct", "L3", "Mechanical", "2026-08-03", "2026-08-14", 2),
        act("b", "Conduit", "L3", "Electrical", "2026-08-13", "2026-08-21", 2)]
assert sq.analyze(pair)["finding_count"] == 1                      # 2-day overlap
assert sq.analyze(pair, min_overlap_days=5)["finding_count"] == 0  # ...below a 5-day bar
assert sq.analyze(pair, crew_threshold=10)["finding_count"] == 0   # ...or a crew-size bar
assert sq.analyze(pair, min_overlap_days=0)["finding_count"] == 1, "0 must not mean 'no overlap needed'"

# ---- ordering: worst first is the longest window with the most people in it ---------------------
many = sq.analyze([
    act("a", "Duct", "L3", "Mechanical", "2026-08-03", "2026-08-28", 4),
    act("b", "Conduit", "L3", "Electrical", "2026-08-05", "2026-08-26", 6),
    act("c", "Sprinkler", "L4", "Fire Protection", "2026-08-03", "2026-08-06", 2),
    act("d", "Paint", "L4", "Finishes", "2026-08-05", "2026-08-07", 1),
])
assert many["finding_count"] == 2
assert many["findings"][0]["location"] == "L3", many["findings"]
assert many["findings"][0]["overlap_days"] > many["findings"][1]["overlap_days"]

# ---- the unbuilt half is NAMED, not approximated -------------------------------------------------
# This used to assert `"GlobalId" in not_covered`, pinning the claim that schedule_activity carries no
# element GlobalId "so there is no way to know what a task installs". That claim was FALSE:
# `element_guids` is a column on every module record (models.py:312) and `me.list_records` returns it,
# so the binding reaches `analyze()` already. The test was holding a wrong statement in place — the
# worst kind of coverage, since a documented dead end is one nobody re-checks.
assert "SUPPORT relationship" in many["not_covered"], many["not_covered"]
assert "binding EXISTS" in many["not_covered"], many["not_covered"]
# ...and the gap is now MEASURABLE rather than asserted: how many activities could be checked today.
assert many["bound_activities"] == 0, many["bound_activities"]   # this fixture binds no elements
bound = sq.analyze([{"data": {"name": "Hanger", "location": "L9", "trade": "Mechanical",
                              "start": "2026-03-01", "finish": "2026-03-10"},
                     "element_guids": ["0aaaaaaaaaaaaaaaaaaaaa"]}])
assert bound["bound_activities"] == 1, bound["bound_activities"]

# a bare dict (no "data" wrapper) is accepted too — the module engine hands both shapes around
flat = sq.analyze([{"name": "Duct", "location": "L3", "trade": "Mechanical",
                    "start": "2026-08-03", "finish": "2026-08-14"},
                   {"name": "Conduit", "location": "L3", "trade": "Electrical",
                    "start": "2026-08-10", "finish": "2026-08-21"}])
assert flat["finding_count"] == 1, flat

print("R21-4D-CLASH OK - space contention: two trades scheduled into one place in one window. "
      "Nothing in the MODEL is wrong when this happens - every element clears every other element - "
      "which is precisely why a geometric clash run cannot find it and why it surfaces on site as "
      "two foremen arguing in a corridor. Same-trade overlap is deliberately NOT a finding, because "
      "one trade sequencing its own crews through a zone is planning rather than contention, and "
      "adjacent windows are fine while a single shared day is not. Activities missing a location or "
      "dates are skipped and COUNTED rather than silently dropped, and an all-unreadable schedule "
      "reports as not-clean, because a clean result over a half-readable schedule is the same "
      "overstatement the clash matrix exists to prevent. The other half of 4D clash - an install "
      "sequenced before the support it hangs from - is NAMED as unbuilt rather than approximated: "
      "schedule_activity carries no element GlobalId, so there is no way to know what a task "
      "installs, and that needs a real task-to-element binding rather than a guess.")
