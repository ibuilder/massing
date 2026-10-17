"""LAYOUT-RENUMBER — the field round-trip's join key was a POSITION, and an unmatched file read as a
perfect as-built.

`layout.points()` numbers setout points `P1..` over its own iteration order and carries the element's
IFC **GlobalId** in the Description — `to_penzd_csv` writes that into the D column precisely so the
round-trip stays anchored, and this module's docstring has always said it matches *"by Point-№ /
GlobalId"*. **`layout.verify` matched on the number alone.** The fix was documented and never built.

TWO DEFECTS, AND THE FIRST IS THE REPOSITORY'S FIRST NON-NEGOTIABLE INVERTED
---------------------------------------------------------------------------
1.  **The number is positional.** Re-publish the model, or export with a different `classes` filter,
    and every point is renumbered — so a survey shot against last week's export matches a *different
    element* under the same number, and the deviation is computed against the wrong design point.
    CLAUDE.md's first rule is *"reference model elements by IFC GlobalId, never by transient viewer
    IDs"*, and `P{i}` is a transient id. Replayed below against two exports of one model.

    **The measured severity is worse than the predicted one, and that is recorded because the
    prediction was wrong in the flattering direction.** This gate's first draft expected the
    renumbered comparison to report a false CLEAN. It does not: it compares each footing against the
    column shot carrying the same number, so it reports **two deviations of a full grid bay** — one
    of them on a point that never moved — while the real 100 mm displacement is nowhere in the
    output. *A fabricated 12-metre finding sends a crew out to re-survey; the real defect stays
    invisible.* Predicting a severity and measuring it are two different things.
2.  **Both unmatched sides were dropped in silence.** A design point with no shot was `continue`; a
    shot matching no design point was never looked at. So a file from the wrong floor returned
    `checked: 0`, `out_of_tolerance: []`, `max_deviation_m: 0.0` — **character-for-character what a
    perfect as-built returns.** This is PROGRESS-DARK's defect (`capture_diff` promised "never
    silently dropped" and silently dropped) in a module that sweep never reached. *A sweep is bounded
    by the module list somebody gave it.*

WHY THE PRECEDENCE IS TWO PASSES AND NOT A LOOP
-----------------------------------------------
Every GUID match is taken before any number may claim a shot. A one-pass version lets an early design
point consume by NUMBER a shot that a later point owns by GlobalId — which is the renumbering defect
re-entering through the fallback that exists to survive it. Asserted directly.

Run: cd services/api && PYTHONPATH=src ./.venv/bin/python test_layout_renumber.py
"""
import math

import ifcopenshell
import ifcopenshell.guid

from aec_api import layout

FAILED: list[str] = []


def ok(cond, label):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILED.append(label)


def _model(spec, spacing=6.0):
    """One storey of elements at distinct coordinates. `spec` is `[(ifc_class, name), ...]`.

    TWO CLASSES ARE LOAD-BEARING. `points()` walks `LAYOUT_CLASSES` in declaration order, so the
    renumbering this gate replays only happens when an export's class SET changes — with a single
    class, filtering changes nothing and the first draft of this file asserted a renumbering that
    had not occurred. *A fixture that cannot exhibit the defect reports the tree clean in the same
    words as a tree that is.*
    """
    f = ifcopenshell.file(schema="IFC4")

    def place(x, y, z):
        pt = f.create_entity("IfcCartesianPoint", Coordinates=(float(x), float(y), float(z)))
        ax = f.create_entity("IfcAxis2Placement3D", Location=pt)
        return f.create_entity("IfcLocalPlacement", RelativePlacement=ax)

    storey = f.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="L1",
                             Elevation=0.0)
    els = [f.create_entity(cls, GlobalId=ifcopenshell.guid.new(), Name=nm,
                           ObjectPlacement=place(i * spacing, 0, 0))
           for i, (cls, nm) in enumerate(spec)]
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                    RelatingStructure=storey, RelatedElements=els)
    return f


def shots_from(pts, offsets=None):
    """A total station's file as the exporter produced it: Point-№, E/N/Z and the Description."""
    offsets = offsets or {}
    return [{"number": p["number"], "description": p["description"],
             "e": p["e"] + offsets.get(p["guid"], 0.0), "n": p["n"], "z": p["z"]} for p in pts]


# ── THE PRE-FIX RULE, isolated so it can be replayed on the same inputs ───────────────────────────
def verify_shipped(design, measured, tolerance_m=0.02):
    """`layout.verify` as it shipped: match on `number`, drop both unmatched sides in silence."""
    m = {}
    for r in measured:
        num = str(r.get("number") or "").strip()
        if num:
            m[num] = (float(r.get("e", 0)), float(r.get("n", 0)), float(r.get("z", 0)))
    devs = []
    for p in design:
        mv = m.get(p["number"])
        if mv is None:
            continue
        d = math.dist((p["e"], p["n"], p["z"]), mv)
        devs.append({"number": p["number"], "guid": p["guid"],
                     "deviation_m": round(d, 4), "in_tolerance": d <= tolerance_m})
    bad = [d for d in devs if not d["in_tolerance"]]
    return {"checked": len(devs), "in_tolerance": len(devs) - len(bad), "out_of_tolerance": bad,
            "max_deviation_m": max((d["deviation_m"] for d in devs), default=0.0)}


# ── ① THE RENUMBERING DEFECT, replayed against two exports of ONE model ──────────────────────────
#
# The second export asks for a subset of classes, which is an ordinary thing to do and changes the
# numbering of every point. The survey was shot against the FIRST export.
print("\n-- one model, two exports, and the number means something different in each --")
SPEC = [("IfcColumn", "C-A"), ("IfcColumn", "C-B"),
        ("IfcFooting", "F-A"), ("IfcFooting", "F-B")]
m1 = _model(SPEC)
# EXPORT A: the whole setout. `LAYOUT_CLASSES` lists columns before footings, so F-A is P3.
export_a = layout.points(m1)
# EXPORT B: a later export of the SAME model asking only for footings — an ordinary thing to do, and
# it renumbers F-A from P3 to P1.
export_b = layout.points(m1, ["IfcFooting"])
num_a = {p["guid"]: p["number"] for p in export_a}
num_b = {p["guid"]: p["number"] for p in export_b}
ok(len(export_a) == 4 and len(export_b) == 2,
   f"two exports of one model   A={len(export_a)} points, B={len(export_b)}")
moved = [g for g in num_b if num_a.get(g) != num_b[g]]
ok(bool(moved),
   "PROOF OF REACH: the same element has a different number in each export   "
   + ", ".join(f"{num_a[g]}->{num_b[g]}" for g in moved))

# The survey was shot against EXPORT A, with F-A 100 mm out of position.
fa = next(p for p in export_a if p["guid"] in num_b and num_a[p["guid"]] != num_b[p["guid"]])
survey = shots_from(export_a, offsets={fa["guid"]: 0.10})

shipped = verify_shipped(export_b, survey)
fixed = layout.verify(export_b, survey)
ok(shipped["checked"] == 2,
   f"the pre-fix rule matched two points by number   checked={shipped['checked']}")
# WHAT IT ACTUALLY DOES IS WORSE THAN THE PREDICTION, and measuring it is what showed that. The
# first draft of this assertion expected `out_of_tolerance: []` — a false CLEAN. In fact it compares
# each footing against the COLUMN shot that happens to carry the same number, so it fabricates two
# deviations of a full grid bay AND loses the real 100 mm one. *A fabricated 12-metre finding sends a
# crew out to re-survey; the real defect stays invisible.* **Predicting a severity and measuring it
# are two different things, and the prediction was wrong in the flattering direction.**
shipped_dev = {d["guid"]: d["deviation_m"] for d in shipped["out_of_tolerance"]}
fb = next(p["guid"] for p in export_b if p["guid"] != fa["guid"])
ok(len(shipped_dev) == 2 and fb in shipped_dev,
   "PROOF OF REACH: the pre-fix rule reports a point that did NOT move as out of tolerance   "
   f"blamed={len(shipped_dev)} of 2 footings, including the one that never moved")
ok(shipped_dev.get(fb, 0) > 1.0 and abs(shipped_dev.get(fa["guid"], 0) - 0.10) > 1.0,
   "...and both magnitudes are a full grid bay rather than the real 100 mm   "
   f"{sorted(round(v, 2) for v in shipped_dev.values())} m vs the actual 0.1 m")
bad_fixed = {d["guid"]: d["deviation_m"] for d in fixed["out_of_tolerance"]}
ok(set(bad_fixed) == {fa["guid"]} and abs(bad_fixed[fa["guid"]] - 0.10) < 0.001,
   f"...while the fixed rule finds exactly the footing that moved, by its real amount   "
   f"{bad_fixed[fa['guid']] if fa['guid'] in bad_fixed else '-'} m")
ok(all(d["matched_on"] == "guid" for d in fixed["deviations"]),
   "...because every point matched on its GlobalId, which the Description carried all along")
ok(fixed["matched_on_guid"] == len(fixed["deviations"]) and fixed["matched_on_number"] == 0,
   f"and the response SAYS which key matched   guid={fixed['matched_on_guid']} "
   f"number={fixed['matched_on_number']}")
ok(fixed["unmatched_shots"] == 2,
   f"...and the two column shots, which belong to no footing, are counted rather than consumed   "
   f"unmatched={fixed['unmatched_shots']}")

cols = export_b          # the four-point design set used by the sections below
cols = export_a

# ── ② A FILE THAT MATCHES NOTHING IS NOT A CLEAN AS-BUILT ─────────────────────────────────────────
print("\n-- the wrong floor's survey file --")
other = layout.points(_model([("IfcColumn", "X-1"), ("IfcColumn", "X-2")]))        # different model: different GUIDs AND numbers
foreign = [{"number": f"Q{i}", "description": p["description"], "e": p["e"], "n": p["n"],
            "z": p["z"]} for i, p in enumerate(other, start=1)]
s2 = verify_shipped(cols, foreign)
f2 = layout.verify(cols, foreign)
ok(s2 == {"checked": 0, "in_tolerance": 0, "out_of_tolerance": [], "max_deviation_m": 0.0},
   "PROOF OF REACH: the pre-fix response is identical to a perfect as-built   "
   f"{s2}")
ok(f2["comparable"] is False,
   "...and the fixed response refuses to be read as one: `comparable` is False")
ok(f2["unshot"] == len(cols) and f2["unmatched_shots"] == len(foreign),
   f"both unmatched sides are counted   unshot={f2['unshot']} "
   f"unmatched_shots={f2['unmatched_shots']}")
ok("NOTHING MATCHED" in f2["note"] and "not a clean as-built" in f2["note"],
   "...and the note says it in words, for a reader who only sees the note")
ok(f2["design_points"] == len(cols) and f2["shots_supplied"] == len(foreign)
   and f2["coverage_pct"] == 0.0,
   f"the population is reported on both sides   design={f2['design_points']} "
   f"shots={f2['shots_supplied']} coverage={f2['coverage_pct']}%")

# ── ③ A PARTIAL SURVEY IS NOT A FULL ONE ──────────────────────────────────────────────────────────
print("\n-- two of four points shot --")
f3 = layout.verify(cols, shots_from(cols[:2]))
ok(f3["checked"] == 2 and f3["unshot"] == 2 and f3["coverage_pct"] == 50.0,
   f"checked {f3['checked']}, unshot {f3['unshot']}, coverage {f3['coverage_pct']}%")
ok(f3["comparable"] is True and not f3["out_of_tolerance"],
   "it IS comparable and nothing is out of tolerance — over half the points")
ok(sorted(f3["unshot_numbers"]) == sorted(p["number"] for p in cols[2:]),
   f"...and it names which points were never shot   {f3['unshot_numbers']}")
ok(f"{f3['checked']} of {f3['design_points']}" in f3["note"],
   "...in the note as well, with the counts")

# ── ④ THE NUMBER FALLBACK STILL WORKS, AND SAYS IT IS A FALLBACK ──────────────────────────────────
#
# A surveyor's instrument that drops the Description column leaves only the number. The comparison
# must still happen — refusing it would break every total station that exports PENZ without D — but
# the response has to say the match was positional.
print("\n-- a file with no Description column --")
no_desc = [{"number": p["number"], "e": p["e"], "n": p["n"], "z": p["z"]} for p in cols]
f4 = layout.verify(cols, no_desc)
ok(f4["checked"] == len(cols) and f4["matched_on_number"] == len(cols),
   f"every point matched, by number   checked={f4['checked']} "
   f"by_number={f4['matched_on_number']}")
ok(f4["matched_on_guid"] == 0 and sorted(f4["number_matched_points"]) == sorted(
    p["number"] for p in cols),
   "...and the points matched positionally are named, not just counted")
ok("positional" in f4["note"] and "fallback" in f4["note"],
   "...and the note says a number match is a match on a position")

# ── ⑤ GUID PRECEDENCE: TWO PASSES, NOT A LOOP ─────────────────────────────────────────────────────
#
# A one-pass matcher lets an early design point claim by NUMBER a shot that a later point owns by
# GlobalId — the renumbering defect re-entering through the very fallback added to survive it.
print("\n-- precedence: a GUID owner must not lose its shot to an earlier number match --")
a, b = cols[0], cols[1]
# One shot, carrying B's GlobalId but A's number. B owns it; A must not take it.
cross = [{"number": a["number"], "description": b["description"],
          "e": b["e"] + 0.10, "n": b["n"], "z": b["z"]}]
f5 = layout.verify([a, b], cross)
ok(f5["checked"] == 1, f"exactly one point compared   checked={f5['checked']}")
ok(f5["deviations"][0]["guid"] == b["guid"] and f5["deviations"][0]["matched_on"] == "guid",
   f"...and it is B, matched on its GlobalId   {f5['deviations'][0]['matched_on']}")
ok(f5["unshot"] == 1 and f5["unshot_numbers"] == [a["number"]],
   f"...while A is reported as unshot rather than compared against B's shot   "
   f"{f5['unshot_numbers']}")

# ── ⑥ THE GUID IS READ FROM THE DESCRIPTION THE EXPORTER WROTE ────────────────────────────────────
print("\n-- the exporter's own CSV round-trips --")
csv_txt = layout.to_penzd_csv(cols, order="PENZD")
rows = [dict(zip(("number", "e", "n", "z", "description"), ln.split(",")))
        for ln in csv_txt.strip().splitlines()[1:]]
f6 = layout.verify(cols, rows)
ok(f6["checked"] == len(cols) and f6["matched_on_guid"] == len(cols),
   f"the file this module EXPORTS matches back by GlobalId   guid={f6['matched_on_guid']}")
ok(max(d["deviation_m"] for d in f6["deviations"]) == 0.0,
   "...with zero deviation, since it is the design re-read")
# And a tag containing a pipe must not fabricate a GUID: the pattern is anchored to the line end and
# length-exact, so only the real trailing GlobalId can match.
ok(layout._DESC_GUID.search("COL-A|B|not22chars") is None,
   "a short trailing field is not mistaken for a GlobalId")
ok(layout._DESC_GUID.search(f"COL-A|weird|{cols[0]['guid']}").group(1) == cols[0]["guid"],
   "...and a tag containing a pipe still yields the real one")

print()
if FAILED:
    print(f"layout_renumber: {len(FAILED)} FAILED — {FAILED}")
    raise SystemExit(1)
print("LAYOUT-RENUMBER OK - the as-installed verify matches by GlobalId first (recovered from the "
      "Description the exporter writes) and by Point-No only as a named fallback, because the number "
      "is positional: the pre-fix rule is replayed and must blame the WRONG element after a "
      "re-export before the gate reports. Both unmatched sides are now counted and `comparable` is "
      "False when nothing matched, so a wrong-floor survey file can no longer return the "
      "character-for-character response of a perfect as-built. GUID precedence is two passes, so a "
      "number match cannot steal a shot its GlobalId owner is entitled to.")
