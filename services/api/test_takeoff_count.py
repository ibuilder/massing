"""R34-TAKEOFF-COUNT — the platform can count, and a count is never scaled.

`_UNIT_LABEL` was `{"area": "m²", "length": "m"}` and every assembly was one or the other, so a door,
a fixture, a receptacle or a sprinkler head — the operation an estimator performs most often — could
not be taken off a drawing at all.

The load-bearing assertion here is not that counting works. It is that **a count does not move with
the scale.** Area goes as scale², length as scale¹, a count as scale⁰. Multiplying a count by a scale
produces a plausible non-integer ("7.3 doors") that prices cleanly and is wrong — and this ring has
already shipped one fix for a mis-scaled plan, so the way such a number travels is not hypothetical.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_takeoff_count.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.takeoff2d import TAKEOFF_ASSEMBLIES, quantify  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


MARK = [[50, 50]]                                   # a count marker is a point
SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]

# --- 1. the measure exists at all -----------------------------------------------------------------
counts = {k: v for k, v in TAKEOFF_ASSEMBLIES.items() if v[0] == "count"}
check("count assemblies exist", len(counts) >= 6, sorted(counts))
check("  including the ones an estimator actually counts",
      {"door", "window", "plumbing_fixture", "receptacle", "light_fixture",
       "sprinkler_head"} <= set(counts), sorted(counts))
check("  and a generic fallback", "generic_count" in counts)

one = quantify([{"category": "door", "points": MARK}], 0.01)
r = one["regions"][0]
check("a single door marker counts as one", r["quantity"] == 1.0, r["quantity"])
check("  its unit is `ea`, not a length or an area", r["unit"] == "ea", r["unit"])
check("  and it is priced per each", r["cost"] == r["quantity"] * r["rate"], (r["cost"], r["rate"]))

# --- 2. THE RULE: a count does not move with the scale ---------------------------------------------
# Same markers, wildly different scales. An area would differ by the square of the ratio.
for scale in (0.001, 0.01, 0.5, 12.0):
    q = quantify([{"category": "door", "points": MARK},
                  {"category": "door", "points": MARK}], scale)
    check(f"two doors are two doors at scale {scale}",
          q["regions"][0]["quantity"] == 1.0 and q["by_assembly"][0]["quantity"] == 2.0,
          (scale, q["by_assembly"][0]["quantity"]))

# contrast, on the same call: the area DOES move and the count does not
mixed = quantify([{"category": "door", "points": MARK},
                  {"category": "generic_area", "points": SQUARE}], 0.01)
mixed2 = quantify([{"category": "door", "points": MARK},
                   {"category": "generic_area", "points": SQUARE}], 0.02)
d1 = next(r for r in mixed["regions"] if r["category"] == "door")
d2 = next(r for r in mixed2["regions"] if r["category"] == "door")
a1 = next(r for r in mixed["regions"] if r["category"] == "generic_area")
a2 = next(r for r in mixed2["regions"] if r["category"] == "generic_area")
check("doubling the scale leaves the count identical", d1["quantity"] == d2["quantity"] == 1.0,
      (d1["quantity"], d2["quantity"]))
check("  while the area on the same call quadruples — scale⁰ against scale²",
      abs(a2["quantity"] - 4 * a1["quantity"]) < 1e-9, (a1["quantity"], a2["quantity"]))
check("a count is never fractional, which is what a scaled count would produce",
      float(d1["quantity"]).is_integer(), d1["quantity"])

# a region's OWN scale must not move a count either — the per-region path is the newer one
own = quantify([{"category": "door", "points": MARK, "scale_units_per_px": 7.5}], 0.01)
check("a region carrying its own scale still counts as one",
      own["regions"][0]["quantity"] == 1.0, own["regions"][0]["quantity"])
check("  and the scale it carries is still RECORDED, just not applied",
      own["regions"][0]["scale_applied"] == 7.5
      and own["regions"][0]["scale_source"] == "region", own["regions"][0])

# --- 3. multiplicity is READ, never inferred from geometry -----------------------------------------
many = quantify([{"category": "receptacle", "points": MARK, "count": 12}], 0.01)
check("a marker may stand for several, when it says so",
      many["regions"][0]["quantity"] == 12.0, many["regions"][0]["quantity"])
check("  and is priced accordingly",
      many["regions"][0]["cost"] == 12 * many["regions"][0]["rate"], many["regions"][0])

# The refusals: anything that is not a positive whole number falls back to ONE, because the marker
# exists — what is unknown is the multiplicity, not the presence.
for bad, why in ((0, "zero markers is not what a placed marker means"),
                 (-3, "a negative count is not a quantity"),
                 (2.5, "a fractional count cannot be ordered"),
                 ("12", "a numeric string is client type-confusion, not a measurement"),
                 (True, "JSON true is not one item"),
                 (float("inf"), "infinity is not a count"),
                 (None, "absent means one marker, one item")):
    q = quantify([{"category": "door", "points": MARK, "count": bad}], 0.01)
    check(f"count={bad!r} falls back to 1 — {why}", q["regions"][0]["quantity"] == 1.0,
          q["regions"][0]["quantity"])

# --- 4. counts roll up separately from geometry ----------------------------------------------------
mix = quantify([
    {"category": "door", "points": MARK},
    {"category": "door", "points": MARK, "count": 3},
    {"category": "generic_area", "points": SQUARE},
], 0.01)
doors = next(a for a in mix["by_assembly"] if a["category"] == "door")
check("count subtotals sum the items, not the markers", doors["quantity"] == 4.0, doors)
check("  and the marker count is separate from the item count", doors["count"] == 2, doors)
check("  the count subtotal keeps its own unit", doors["unit"] == "ea", doors["unit"])
check("  areas are untouched by the count assemblies being present",
      next(a for a in mix["by_assembly"] if a["category"] == "generic_area")["unit"] == "m²")
check("the grand total includes both kinds",
      mix["total_cost"] == round(sum(r["cost"] for r in mix["regions"]), 2), mix["total_cost"])

# --- 5. the assembly catalogue advertises the new measure -------------------------------------------
adv = {a["category"]: a for a in one["assemblies"]}
check("the catalogue lists count assemblies with their unit",
      adv["door"]["measure"] == "count" and adv["door"]["unit"] == "ea", adv.get("door"))
check("  and still lists area/length ones correctly",
      adv["generic_area"]["unit"] == "m²" and adv["generic_linear"]["unit"] == "m")

# --- 6. additive — measure provenance still applies to counts ---------------------------------------
prov = quantify([{"category": "door", "points": MARK,
                  "method": "one_click", "measured_by": "agent"}], 0.01)["regions"][0]
check("a counted marker carries its provenance like any other measurement",
      (prov["method"], prov["measured_by"]) == ("one_click", "agent"),
      (prov["method"], prov["measured_by"]))
check("  and an unstated one is still `unrecorded`",
      quantify([{"category": "door", "points": MARK}], 0.01)["regions"][0]["method"] == "unrecorded")

print()
if FAILED:
    print(f"takeoff_count: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("takeoff_count: all checks passed")
