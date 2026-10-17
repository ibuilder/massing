"""CAPTURE-SESSION — a capture at a moment, derived from a register that already exists.

`POST /projects/{pid}/progress/capture-diff` had no caller, and the reason was written down and
measured: *"nothing in this product persists a capture… a screen would have to invent the concept —
a stored capture with a date and a GUID set — which is a product decision and a migration, not a
wiring job."*

**Half of that was right.** It is true of a stored capture ROW. It is not true of the SET: every
`field_verification` record carries a REQUIRED `guid` and an `observed_date`, so *"what was observed
installed as of 2026-09-30"* is a filter over a register this product has had all along. *"There is
no stored X" and "X is not available" are different claims, and a measured blocker can state the
first while reading as the second.*

The other option that entry named could not have worked, and this file records why so nobody costs
it again: *"let the CV bridge's ingest-batch writes become the capture record, which gets the
timestamps for free"* — that bridge's payload is `{activity, percent}` and carries no element
identity at all. **An unblocking option nobody costed is a plan with a hole in it.**

WHAT THE DERIVATION COSTS
-------------------------
It is CUMULATIVE (`observed_date <= as_of`) and that was forced, not preferred. A point-in-time
reading would report every element not re-verified on the later date as *disappeared*, manufacturing
rework flags out of a crew's ordinary habit of not re-walking finished work. So the set can only
grow, `disappeared` is empty BY CONSTRUCTION, and `derived.cumulative` says so — because a consumer
must SUPPRESS the rework half rather than draw an empty table, which reads as "no rework found", the
opposite of "this source cannot tell you". *Choosing which half to make unreachable is better than
leaving a half that lies.*

Run: PYTHONPATH=src ./.venv/bin/python test_capture_derived.py
"""
import json
import os
import shutil

os.environ["DATABASE_URL"] = "sqlite:///./test_capture_derived.db"
os.environ["STORAGE_DIR"] = "./test_storage_capture_derived"
os.environ["IFC_DIR"] = "./test_ifc_capture_derived"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_capture_derived.db",):
    if os.path.exists(f):
        os.remove(f)
if os.path.isdir("./test_storage_capture_derived"):
    shutil.rmtree("./test_storage_capture_derived")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.progress_rollup import installed_as_of  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        FAILURES.append(name)


# ── the derivation, pure ──────────────────────────────────────────────────────────────────────────
RECS = [{"data": {"guid": g, "observed_date": d}} for g, d in [
    ("W1", "2026-09-01"), ("W2", "2026-09-10"), ("S1", "2026-09-12"),
    ("W3", "2026-09-25"), ("D1", "2026-09-28"), ("GHOST", "2026-09-29"),
    ("W1", "2026-10-05"),                     # the same element observed twice
]]
RECS.append({"data": {"guid": "B1"}})         # observed, never dated
RECS.append({"data": {"guid": "", "observed_date": "2026-09-01"}})   # dated, no element

mid = installed_as_of(RECS, "2026-09-15")
check("a cutoff takes every element observed ON OR BEFORE it",
      mid["guids"] == ["S1", "W1", "W2"], f"{mid['guids']}")
check("...and an element observed twice counts once",
      mid["count"] == 3 and installed_as_of(RECS, "2026-12-31")["count"] == 6,
      f"{mid['count']} / {installed_as_of(RECS, '2026-12-31')['count']}")
check("an UNDATED verification is excluded and COUNTED, never silently dropped",
      mid["undated"] == 1 and "B1" not in mid["guids"],
      f"undated={mid['undated']} — an undated row is outside EVERY capture at every date, so the "
      f"count is the only thing that makes it findable")
check("a row with no element is skipped without inflating the undated count",
      installed_as_of([{"data": {"guid": "", "observed_date": "2026-09-01"}}], "2026-09-30")
      == {"guids": [], "count": 0, "as_of": "2026-09-30", "undated": 0, "earliest": None,
          "latest": None, "source": "field_verification",
          "note": installed_as_of([], None)["note"]},
      "a blank guid is not a dating problem, and counting it as one sends somebody to fix the wrong "
      "field")

# THE RANGE IS OVER THE REGISTER, NOT OVER THE CUTOFF. An `as_of` before the first observation
# returns an empty set — a correct answer that looks alarming — so the caller needs to be able to
# tell "nothing was built" from "the records start later".
early = installed_as_of(RECS, "2026-08-01")
check("a cutoff before the register begins returns an empty set AND the register's real range",
      early["count"] == 0 and early["earliest"] == "2026-09-01" and early["latest"] == "2026-10-05",
      f"{early['count']} / {early['earliest']}..{early['latest']}")
check("a null cutoff means every dated record, which is the 'as of now' reading",
      installed_as_of(RECS, None)["count"] == 6,
      f"{installed_as_of(RECS, None)['count']}")

# MONOTONICITY, asserted rather than asserted-about: this is what makes `disappeared` structurally
# empty, and the whole consumer contract rests on it.
seq = [installed_as_of(RECS, d)["count"]
       for d in ("2026-09-01", "2026-09-12", "2026-09-28", "2026-10-05")]
check("the derived set is MONOTONIC, which is why the rework half is unanswerable from it",
      seq == sorted(seq) and seq == [1, 3, 5, 6],
      f"{seq} — a point-in-time reading would make this non-monotonic and turn every un-rewalked "
      f"element into a false rework flag")

# ── the route ─────────────────────────────────────────────────────────────────────────────────────
#
# **THE REGISTER VALIDATES THE GUID, which the short names above would never have shown.** A POST of
# `{"guid": "W1"}` is refused 422: *"'W1' is not an IFC GlobalId (22 chars over [0-9A-Za-z_$])"*.
# That is the top-level non-negotiable enforced at the door — reference an element by GlobalId, never
# by a transient id — and it is the reason this derivation is sound at all: the register cannot hold
# a key the model could not match. The pure section above keeps short names because it is a test of
# the FILTER and reads better for it; everything that goes through the door uses real ones.
_G = {
    "W1": "1aBcDeFgHiJkLmNoPqRs01", "W2": "1aBcDeFgHiJkLmNoPqRs02",
    "W3": "1aBcDeFgHiJkLmNoPqRs03", "S1": "1aBcDeFgHiJkLmNoPqRs04",
    "D1": "1aBcDeFgHiJkLmNoPqRs05", "B1": "1aBcDeFgHiJkLmNoPqRs06",
    "GHOST": "1aBcDeFgHiJkLmNoPqRs99",
}
PROPS = {
    "schema": "demo", "project": {"name": "Capture Tower"},
    "elements": [{"guid": _G[g], "ifc_class": c, "storey": s} for g, c, s in [
        ("W1", "IfcWall", "L1"), ("W2", "IfcWall", "L1"), ("W3", "IfcWall", "L2"),
        ("S1", "IfcSlab", "L1"), ("D1", "IfcDoor", "L2"), ("B1", "IfcBeam", "L2")]],
}
#: The same observations as `RECS`, keyed by GlobalId so the register will accept them. `GHOST` is
#: deliberately NOT in `PROPS`: a verification against a model version this project no longer has.
WIRE = [{"guid": _G[g], "observed_date": d} for g, d in [
    ("W1", "2026-09-01"), ("W2", "2026-09-10"), ("S1", "2026-09-12"),
    ("W3", "2026-09-25"), ("D1", "2026-09-28"), ("GHOST", "2026-09-29"),
    ("W1", "2026-10-05"),
]] + [{"guid": _G["B1"]}]

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Capture Tower"}).json()["id"]
    up = c.post(f"/projects/{pid}/properties/index",
                files={"file": ("props.json", json.dumps(PROPS).encode(), "application/json")})
    assert up.status_code == 200, up.text[:200]

    # A non-GlobalId guid is REFUSED at the door, which is what makes the derivation sound: the
    # register cannot hold a key the model could not match.
    bad = c.post(f"/projects/{pid}/modules/field_verification",
                 json={"data": {"guid": "W1", "observed_date": "2026-09-01"}})
    check("the register refuses a guid that is not an IFC GlobalId",
          bad.status_code == 422 and "GlobalId" in bad.text,
          f"{bad.status_code} {bad.text[:120]}")

    for row in WIRE:
        got = c.post(f"/projects/{pid}/modules/field_verification", json={"data": row})
        assert got.status_code == 201, (got.status_code, got.text[:200])

    # OPT-IN, NEVER A FALLBACK. Without `derive`, an absent `installed_t1` means the caller sent
    # nothing — and answering a different question than the one asked is how a screen comes to show
    # a diff over a set nobody chose.
    plain = c.post(f"/projects/{pid}/progress/capture-diff", json={}).json()
    check("without `derive`, the route still answers over the sets it was given (none)",
          plain["installed_t1"] == 0 and plain["installed_t2"] == 0 and plain["derived"] is None,
          f"{plain['installed_t1']}/{plain['installed_t2']} derived={plain['derived']}")

    d = c.post(f"/projects/{pid}/progress/capture-diff",
               json={"derive": "field_verification", "t1": "2026-09-15", "t2": "2026-09-30"})
    check("the route derives both sets from the register", d.status_code == 200, d.text[:200])
    dj = d.json()
    check("...and the diff is the real delta between the two dates",
          dj["newly_installed"] == 2 and dj["added_guids"] == sorted([_G["D1"], _G["W3"]]),
          f"{dj['newly_installed']} {dj['added_guids']}")
    check("...grouped by class and by level, which is what a superintendent reads",
          dj["added_by_level"] == [{"storey": "L2", "count": 2}]
          and {x["ifc_class"] for x in dj["added_by_class"]} == {"IfcWall", "IfcDoor"},
          f"{dj['added_by_class']} / {dj['added_by_level']}")
    check("...with the window and the daily rate",
          dj["days"] == 15 and dj["elements_per_day"] is not None,
          f"days={dj['days']} rate={dj['elements_per_day']}")

    # THE PROVENANCE, which `fived`-style the engine cannot know: it receives two lists.
    dv = dj["derived"]
    check("the response says where the sets came from",
          dv and dv["source"] == "field_verification", f"{dv}")
    check("...and the count on each SIDE, keyed to its own date",
          dv["t1"] == {"as_of": "2026-09-15", "count": 3}
          and dv["t2"] == {"as_of": "2026-09-30", "count": 6},
          f"{dv['t1']} / {dv['t2']}")
    check("...and the undated verifications, which no capture can ever use",
          dv["undated"] == 1, f"{dv['undated']}")
    check("...and that the derivation is cumulative, so the rework half is unanswerable",
          dv["cumulative"] is True and dj["disappeared"] == 0 and dj["disappeared_guids"] == [],
          f"cumulative={dv['cumulative']} disappeared={dj['disappeared']}")
    check("...and the register's own dated range, so an empty side is explicable",
          dv["register_earliest"] == "2026-09-01" and dv["register_latest"] == "2026-10-05",
          f"{dv['register_earliest']}..{dv['register_latest']}")

    # GHOST is in the register and not in the model: PROGRESS-DARK's correction, reached through the
    # new door. A capture aimed at the wrong model version must be visible rather than arrive as a
    # quietly smaller diff.
    check("a verified GUID the model does not know is reported, not absorbed",
          dj["unmatched_t2"] == 1 and _G["GHOST"] in dj["unmatched_guids"],
          f"unmatched_t2={dj['unmatched_t2']} {dj['unmatched_guids']}")

    # A date before the register begins: an honest empty side.
    before = c.post(f"/projects/{pid}/progress/capture-diff",
                    json={"derive": "field_verification", "t1": "2026-01-01",
                          "t2": "2026-09-30"}).json()
    check("a date before the first observation gives an empty side and the range to explain it",
          before["derived"]["t1"]["count"] == 0
          and before["derived"]["register_earliest"] == "2026-09-01",
          f"{before['derived']['t1']} earliest={before['derived']['register_earliest']}")

    # An unknown `derive` value is NOT silently honoured as the known one.
    bogus = c.post(f"/projects/{pid}/progress/capture-diff",
                   json={"derive": "tea_leaves", "t1": "2026-09-15", "t2": "2026-09-30"}).json()
    check("an unknown `derive` source derives NOTHING rather than guessing which one was meant",
          bogus["derived"] is None and bogus["installed_t2"] == 0,
          f"derived={bogus['derived']} installed_t2={bogus['installed_t2']}")

print()
if FAILURES:
    print(f"capture_derived: {len(FAILURES)} FAILED — {FAILURES}")
    sys.exit(1)
print("capture_derived: all checks passed — a capture at a moment is a FILTER over the Field "
      "Verification register, not a concept this product lacks. The derivation is cumulative on "
      "purpose, so `disappeared` is empty by construction and the response says so, because a "
      "consumer must suppress the rework half rather than draw an empty table that reads as 'no "
      "rework found'.")
