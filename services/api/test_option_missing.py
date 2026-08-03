"""R22-OPTION-OBJECT — a MISSING criterion is not a good score.

`_evaluate` sets `cost_per_sf` from `(est.get("metrics") or {}).get("cost_per_sf")`, so it can be
None. `score_options` then did `float(r["cost_per_sf"] or 0.0)` and normalized it. On a
lower-is-better axis **0 is the minimum**, so an option with NO cost data normalized to **100 — the
best possible cost score, awarded for having no data** — and outranked every option that carried a
real number. In an engine whose entire job is telling a developer which massing to take into design,
that is the worst available failure: it recommends the option nobody priced.

Measured before the fix, with a real $300/sf and $450/sf option in the set:

    option WITHOUT cost data -> 100.0
    option at $300/sf        ->  33.3
    option at $450/sf        ->   0.0

The fix is the one this module already applies to mixed carbon bases — exclude, then say so:

1. a missing value is **excluded from the normalization pool**, so it cannot set the min/max;
2. its criterion scores **None**, never a number, because averaging it in as 0 or 100 states
   something about the option that nobody measured;
3. the composite is taken over the criteria the option **has**, with weights renormalized;
4. it is **ranked but cannot be recommended** — recommending an option scored on fewer dimensions
   than its rivals is a massing evaluated without its returns, which is the failure this ring is
   named for.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_option_missing.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import option_score  # noqa: E402
from aec_api.option_score import _norm, _num, score_options  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- the coercion that caused it --------------------------------------------------------------------
check("_num refuses None rather than coercing it to zero", _num(None) is None)
check("  and refuses '' , bool and non-finite too",
      _num("") is None and _num(True) is None and _num(float("inf")) is None and _num(float("nan")) is None)
check("  but a real zero IS a number — a $0 cost is data, not absence", _num(0) == 0.0)
check("THE OLD COERCION WOULD HAVE SCORED A MISSING COST BEST",
      _norm([0.0, 300.0, 450.0], 0.0, higher_better=False) == 100.0,
      "this is the defect, asserted so nobody reintroduces float(x or 0)")

# --- driven through score_options via a controlled _evaluate ------------------------------------------
ROWS = [
    {"label": "priced-cheap", "cost_per_sf": 300.0, "carbon_intensity_kgco2e_m2": 400.0,
     "yield_net_sellable_m2": 1000.0, "compliant": True, "carbon_basis": "quantity"},
    {"label": "priced-dear", "cost_per_sf": 450.0, "carbon_intensity_kgco2e_m2": 500.0,
     "yield_net_sellable_m2": 1200.0, "compliant": True, "carbon_basis": "quantity"},
    {"label": "unpriced", "cost_per_sf": None, "carbon_intensity_kgco2e_m2": 450.0,
     "yield_net_sellable_m2": 1100.0, "compliant": True, "carbon_basis": "quantity"},
]
_real = option_score._evaluate
option_score._evaluate = lambda o: dict(ROWS[o["_i"]])            # noqa: E731 — focused seam
try:
    out = score_options([{"_i": i} for i in range(len(ROWS))])
finally:
    option_score._evaluate = _real

by = {r["label"]: r for r in out["options"]}
check("the unpriced option's COST score is None, not 100",
      by["unpriced"]["scores"]["cost"] is None, by["unpriced"]["scores"])
check("  it is flagged as missing that criterion",
      by["unpriced"]["missing_criteria"] == ["cost"], by["unpriced"]["missing_criteria"])
check("  and marked not fully scored", by["unpriced"]["fully_scored"] is False)
check("the priced options keep real cost scores",
      by["priced-cheap"]["scores"]["cost"] == 100.0 and by["priced-dear"]["scores"]["cost"] == 0.0,
      {k: by[k]["scores"]["cost"] for k in ("priced-cheap", "priced-dear")})
check("  normalization used ONLY the present values — the cheapest priced option is the best",
      by["priced-cheap"]["scores"]["cost"] == 100.0)
check("the other criteria still score for the unpriced option",
      by["unpriced"]["scores"]["carbon"] is not None
      and by["unpriced"]["scores"]["yield"] is not None, by["unpriced"]["scores"])

check("AN UNSCORED OPTION CANNOT BE RECOMMENDED", out["recommended"] != "unpriced",
      out["recommended"])
check("  a fully-scored compliant option is recommended instead",
      out["recommended"] in ("priced-cheap", "priced-dear"), out["recommended"])
check("  it is still RANKED, not hidden — a reader may want to see it",
      "unpriced" in {r["label"] for r in out["options"]})
check("  and the result names the partially-scored options",
      out["partially_scored"] == ["unpriced"], out.get("partially_scored"))
check("  with a note saying why they cannot be recommended",
      "measured on fewer dimensions" in (out.get("partially_scored_note") or ""),
      out.get("partially_scored_note"))

# a fully-populated set must be unaffected — the fix must not change ordinary scoring
_real = option_score._evaluate
option_score._evaluate = lambda o: dict(ROWS[o["_i"]])            # noqa: E731
try:
    clean = score_options([{"_i": i} for i in (0, 1)])
finally:
    option_score._evaluate = _real
check("a set with no missing data is scored exactly as before",
      all(r["fully_scored"] for r in clean["options"])
      and clean["partially_scored"] == [] and clean["recommended"] == "priced-cheap",
      (clean["recommended"], clean["partially_scored"]))
check("  and no partial note is emitted when nothing is partial",
      clean["partially_scored_note"] == "", clean["partially_scored_note"])

print()
if FAILED:
    print(f"option_missing: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("option_missing: all checks passed")
