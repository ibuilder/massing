"""Takeoff pricing — price quantities from the built-in book + variance vs estimate; live bridge off.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_pricing.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_pricing.db"
os.environ["STORAGE_DIR"] = "./test_storage_pricing"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("PRICING_PROVIDER", None)
for _f in ("./test_pricing.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import pricing, pricing_bridge  # noqa: E402
from aec_api.main import app  # noqa: E402

assert pricing_bridge.is_enabled() is False and pricing_bridge.unit_price("concrete", "cy") is None

# --- engine ---
r = pricing.reconcile([
    {"description": "concrete footings", "quantity": 100, "unit": "cy", "estimated_unit_price": 200, "cost_code": "03-3000"},
    {"description": "drywall", "quantity": 5000, "unit": "sf"},
    {"description": "concrete", "quantity": 10, "unit": "kg"},          # unit != book unit (cy) -> flagged
    {"description": "unobtainium", "quantity": 3, "unit": "ea"},        # no match
])
concrete = r["lines"][0]
assert concrete["priced_amount"] == 100 * 185.0 and concrete["source"] == "book", concrete
# estimate was $200/cy vs book $185 -> negative variance (book cheaper)
assert concrete["variance"] == round(100 * 185 - 100 * 200, 2) and concrete["variance_pct"] == -7.5, concrete
assert r["lines"][1]["priced_amount"] == 5000 * 2.75, r["lines"][1]
assert r["lines"][2]["priced_amount"] is None and "unit" in r["lines"][2]["note"], r["lines"][2]
assert r["lines"][3]["matched"] is None, r["lines"][3]
assert r["matched"] == 2 and r["pricing_source"] == "book", r
assert r["priced_total"] == round(100 * 185 + 5000 * 2.75, 2), r

# --- endpoint from production_quantity ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    c.post(f"/projects/{pid}/modules/production_quantity",
           json={"data": {"description": "CMU wall", "quantity": 2000, "unit": "sf", "cost_code": "04-2000"}})
    pr = c.get(f"/projects/{pid}/pricing/reconcile").json()
    assert pr["matched"] == 1 and pr["priced_total"] == 2000 * 13.5, pr
    assert c.get("/pricing/status").json()["enabled"] is False

# ---- PRICE-MATCHED: the summary's variance must agree with the lines it is built from ----------
#
# The fixture at the top of this file is the defective shape, and this file already asserted the
# right thing ONE LEVEL DOWN: `concrete["variance"] == round(100 * 185 - 100 * 200, 2)`, commented
# "negative variance (book cheaper)". The SUMMARY contradicted it. `variance_total` was
# `priced_total - est_total`, and those are totals over different populations -- `priced_total` is
# every matched line, `est_total` only the subset also carrying an estimated unit price -- so on
# exactly this input it returned **+4250** where the comparable variance is **-1500**. The sign was
# wrong, and the analytics card renders a positive variance in `--status-warn` red, so the screen
# showed an overrun where the book is cheaper.
#
# *A test that is right at the row level and silent at the summary level reads exactly like a test
# of the summary.* So the assertion below is DERIVED from the per-line figures rather than from a
# number written out here: with one comparable line, the summary must equal that line's own
# `variance`, sign included.
_cmp = [ln for ln in r["lines"] if ln.get("variance") is not None]
assert len(_cmp) == 1, f"this fixture is meant to have exactly one comparable line: {len(_cmp)}"
assert r["comparable_line_count"] == 1, r["comparable_line_count"]
assert r["variance_total"] == _cmp[0]["variance"], (r["variance_total"], _cmp[0]["variance"])
assert r["variance_total"] < 0, f"the book is cheaper here; a positive total is the old defect: {r['variance_total']}"
# ...and it is NOT the old arithmetic, which this fixture makes a different number.
assert r["variance_total"] != round(r["priced_total"] - r["estimated_total"], 2), \
    "variance_total still equals priced_total - estimated_total on a fixture where they differ"

# The three populations the engine computed and used to discard. `matched` counts PRICED lines, so
# the unit-mismatch row is excluded from it while its own `matched` field names the book keyword --
# two senses of one word, and `unit_mismatch` is exactly the difference.
assert (r["matched"], r["unmatched"], r["unit_mismatch"], r["line_count"]) == (2, 1, 1, 4), r
assert r["matched"] + r["unmatched"] + r["unit_mismatch"] == r["line_count"], r
assert r["lines"][2]["matched"] == "concrete" and r["lines"][2]["priced_amount"] is None, r["lines"][2]

# `comparable_priced_total` is the other side of the subtraction, published so a reader can see
# which total the variance came out of.
assert r["comparable_priced_total"] == _cmp[0]["priced_amount"], r["comparable_priced_total"]
assert r["comparable_priced_total"] != r["priced_total"], "the fixture no longer distinguishes them"

# COVERAGE: 3 of 400 priced and 3 of 3 priced returned identical text on the card. The note is the
# engine's own sentence about which lines the totals are over.
_many = pricing.reconcile([{"description": f"unobtainium {i}", "quantity": 10, "unit": "ea",
                    "estimated_unit_price": 100} for i in range(397)]
                  + [{"description": "concrete", "quantity": 100, "unit": "cy",
                      "estimated_unit_price": 90} for _ in range(3)])
_few = pricing.reconcile([{"description": "concrete", "quantity": 100, "unit": "cy",
                   "estimated_unit_price": 90} for _ in range(3)])
assert _many["matched"] == _few["matched"] == 3, (_many["matched"], _few["matched"])
assert _many["priced_total"] == _few["priced_total"], "the two cases must still have equal totals"
assert _many["variance_total"] == _few["variance_total"], "...and equal variances"
assert _many["coverage_note"] != _few["coverage_note"], "the two cases are still one sentence"
assert "3 of 400" in _many["coverage_note"] and "397" in _many["coverage_note"], _many["coverage_note"]

# No comparable line is not a variance of zero.
_noest = pricing.reconcile([{"description": "concrete", "quantity": 100, "unit": "cy"}])
assert _noest["variance_total"] is None and _noest["comparable_line_count"] == 0, _noest
assert "not a variance of zero" in _noest["coverage_note"], _noest["coverage_note"]

# And the note must not assert a contrast that does not exist: when every priced line is
# comparable, "which is not the N priced lines above" is a false warning, and a spurious warning is
# one a reader learns to skip.
assert "which is not the" not in _many["coverage_note"], _many["coverage_note"]
assert "which is not the" in pricing.reconcile(
    [{"description": "concrete", "quantity": 100, "unit": "cy", "estimated_unit_price": 90}]
    + [{"description": "concrete", "quantity": 100, "unit": "cy"} for _ in range(4)]
)["coverage_note"]


print("PRICING OK - book-priced takeoff (concrete/drywall/cmu); variance vs estimate (-7.5%); unit "
      "mismatch + unmatched material flagged (no guess); live bridge off falls back to the book")
