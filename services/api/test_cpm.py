"""CPM engine: forward/backward pass, total/free float, critical path, cycle safety.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_cpm.py"""
from aec_api import schedule_cpm


# Classic network:  A(3)->C, B(2)->C, C(4)->D, D(2).  Critical path A->C->D = 9 days; B has 1 day float.
def act(ref, dur, preds=""):
    return {"id": ref, "ref": ref, "title": ref, "data": {"name": ref, "duration": dur, "predecessors": preds}}

r = schedule_cpm.compute([act("A", 3), act("B", 2), act("C", 4, "A,B"), act("D", 2, "C")])
by = {a["ref"]: a for a in r["activities"]}

assert r["project_duration"] == 9, r["project_duration"]
assert r["has_cycle"] is False
assert by["A"]["es"] == 0 and by["A"]["ef"] == 3 and by["A"]["total_float"] == 0 and by["A"]["critical"]
assert by["B"]["es"] == 0 and by["B"]["ef"] == 2 and by["B"]["total_float"] == 1 and not by["B"]["critical"], by["B"]
assert by["C"]["es"] == 3 and by["C"]["ef"] == 7 and by["C"]["critical"]
assert by["D"]["es"] == 7 and by["D"]["ef"] == 9 and by["D"]["critical"]
assert by["B"]["free_float"] == 1, by["B"]["free_float"]      # B can slip 1 day without delaying C
assert r["critical_path"] == ["A", "C", "D"], r["critical_path"]
assert r["critical_count"] == 3

# duration derived from start/finish when no explicit duration
r2 = schedule_cpm.compute([{"id": "X", "ref": "X", "data": {"start": "2026-01-01", "finish": "2026-01-11"}}])
assert r2["activity_count"] == 1 and r2["activities"][0]["duration"] == 10, r2["activities"][0]

# a cycle is reported, not crashed
r3 = schedule_cpm.compute([act("P", 1, "Q"), act("Q", 1, "P")])
assert r3["has_cycle"] is True and r3["activity_count"] == 2

print("CPM OK - forward/backward pass, total+free float, critical path A-C-D=9d, derived duration, cycle-safe")
