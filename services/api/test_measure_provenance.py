"""R34-MEASURE-PROVENANCE — a takeoff measurement records HOW it was made, or says it does not.

The entry's sentence is exact: *"We record the number."* A quantity with no method, no author and no
scale is indefensible in a claim — and the failure is not that it is missing, it is that a number
recorded without its method looks identical to one recorded with it.

So the assertions here are mostly about the refusals:

1. a region that does not state its method is `unrecorded`, NOT assumed traced;
2. a region that does not state its author is `unrecorded`, NOT assumed a person;
3. the scale that was actually applied is recorded per row, so a mixed-scale takeoff is visible.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_measure_provenance.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.takeoff2d import MEASURE_AUTHORS, MEASURE_METHODS, quantify  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]
LINE = [[0, 0], [100, 0]]

# --- 1. THE REFUSAL: silence is recorded as silence -------------------------------------------------
bare = quantify([{"category": "generic_area", "points": SQUARE}], 0.01)
r0 = bare["regions"][0]
check("a region with no stated method is `unrecorded`, not assumed traced",
      r0["method"] == "unrecorded", r0["method"])
check("  and with no stated author is `unrecorded`, not assumed a person",
      r0["measured_by"] == "unrecorded", r0["measured_by"])
check("  the quantity is still recorded — provenance is missing, the measurement is not",
      r0["quantity"] > 0, r0["quantity"])
check("  and the roll-up NAMES the unrecorded regions rather than only counting them",
      bare["provenance"]["unrecorded_regions"] == [0], bare["provenance"])
check("  recorded_pct is 0 when nothing states its provenance",
      bare["provenance"]["recorded_pct"] == 0.0, bare["provenance"]["recorded_pct"])
check("  the note says the number is recorded either way but its defensibility is not",
      "defensibility" in bare["provenance"]["note"], bare["provenance"]["note"])

# --- 2. stated provenance survives onto the row ------------------------------------------------------
told = quantify([
    {"category": "generic_area", "points": SQUARE, "method": "one_click", "measured_by": "agent"},
    {"category": "generic_length", "points": LINE, "method": "traced", "by": "person"},
], 0.01)
a, b = told["regions"]
check("a one-click agent measurement is recorded as such",
      (a["method"], a["measured_by"]) == ("one_click", "agent"), (a["method"], a["measured_by"]))
check("a hand-traced person measurement is recorded as such",
      (b["method"], b["measured_by"]) == ("traced", "person"), (b["method"], b["measured_by"]))
check("  `by` is accepted as well as `measured_by` — one alias, not a second vocabulary",
      b["measured_by"] == "person")
check("  the roll-up counts by method", told["provenance"]["by_method"]["one_click"] == 1
      and told["provenance"]["by_method"]["traced"] == 1, told["provenance"]["by_method"])
check("  and by author", told["provenance"]["by_author"] == {"person": 1, "agent": 1,
                                                             "unrecorded": 0},
      told["provenance"]["by_author"])
check("  with nothing left unrecorded", told["provenance"]["recorded_pct"] == 100.0)

# --- 3. an unrecognised value is unrecorded, not passed through --------------------------------------
# A free-text method would let anything look like provenance. The vocabulary is closed.
junk = quantify([{"category": "generic_area", "points": SQUARE,
                  "method": "eyeballed it", "measured_by": "the intern"}], 0.01)
j = junk["regions"][0]
check("an unrecognised method is normalised to `unrecorded`, not echoed back",
      j["method"] == "unrecorded", j["method"])
check("  and an unrecognised author likewise", j["measured_by"] == "unrecorded", j["measured_by"])
check("  the vocabularies are closed sets", "unrecorded" in MEASURE_METHODS
      and "unrecorded" in MEASURE_AUTHORS)
check("hyphens and spaces normalise, so `one-click` is not silently discarded",
      quantify([{"category": "generic_area", "points": SQUARE,
                 "method": "one-click"}], 0.01)["regions"][0]["method"] == "one_click")

# --- 4. THE SCALE that was applied is recorded per row -------------------------------------------------
# A wrong scale produces a plausible number, which is why it has to travel with the measurement.
uniform = quantify([{"category": "generic_area", "points": SQUARE}], 0.01)
check("the applied scale is recorded on the row", uniform["regions"][0]["scale_applied"] == 0.01,
      uniform["regions"][0]["scale_applied"])
check("  and its source is stated — the call, not the region",
      uniform["regions"][0]["scale_source"] == "call", uniform["regions"][0]["scale_source"])
check("  a single-scale takeoff is not flagged as mixed",
      uniform["provenance"]["mixed_scales"] is False)

mixed = quantify([
    {"category": "generic_area", "points": SQUARE},                                  # call scale
    {"category": "generic_area", "points": SQUARE, "scale_units_per_px": 0.02},      # its own
], 0.01)
m0, m1 = mixed["regions"]
check("a region carrying its own scale uses it", m1["scale_applied"] == 0.02, m1["scale_applied"])
check("  and says the scale came from the region", m1["scale_source"] == "region")
check("  the quantity reflects the region's scale, not the call's",
      m1["quantity"] > m0["quantity"], (m0["quantity"], m1["quantity"]))
# 100x100 px at 0.02 units/px = 2x2 units = 4; at 0.01 = 1x1 = 1. Area scales with s², so 4x.
check("  and by the square of the ratio for an area measure",
      abs(m1["quantity"] - 4 * m0["quantity"]) < 1e-6, (m0["quantity"], m1["quantity"]))
check("MIXED scales are flagged — real plan sets mix them, and a reviewer must see it",
      mixed["provenance"]["mixed_scales"] is True, mixed["provenance"]["scales_used"])
check("  with the scales named", sorted(mixed["provenance"]["scales_used"]) == [0.01, 0.02],
      mixed["provenance"]["scales_used"])

# --- 5. bad input is absent, not favourable -----------------------------------------------------------
for bad in (0, -1, "wide", None):
    q = quantify([{"category": "generic_area", "points": SQUARE, "scale_units_per_px": bad}], 0.01)
    check(f"an invalid region scale ({bad!r}) falls back to the call's, never to zero",
          q["regions"][0]["scale_applied"] == 0.01 and q["regions"][0]["scale_source"] == "call",
          (q["regions"][0]["scale_applied"], q["regions"][0]["scale_source"]))

check("an empty takeoff reports 0% rather than dividing by zero",
      quantify([], 0.01)["provenance"]["recorded_pct"] == 0.0)

# --- 6. additive — the pre-existing shape is untouched -------------------------------------------------
check("the original row fields still mean what they meant",
      all(k in r0 for k in ("index", "category", "assembly", "measure", "quantity", "unit",
                            "rate", "cost")), sorted(r0))
check("  and the assembly roll-up is unchanged",
      bare["by_assembly"][0]["quantity"] == r0["quantity"], bare["by_assembly"][0])

print()
if FAILED:
    print(f"measure_provenance: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("measure_provenance: all checks passed")
