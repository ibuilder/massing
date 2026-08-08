"""QTO-TRADE — a model-derived QTO line can be bought out, and the trade comes from the spine.

WHAT WAS WRONG, AND WHY IT LOOKED LIKE A MISSING FEATURE. `buyout_packages` read a hand-entered
estimate line's spelling and only that: `item`/`description`/`material` for identity, `qty` for
quantity, `unit_price` for price, `trade` for the package. `element_5d` emits a model-derived line as
`{guid, name, ifc_class, storey, basis, quantity, rate, cost}` — none of those names. Every line hit
`if not item: continue`, so a fully-priced model produced **zero packages and zero cost**.

That is why four procurement client methods were filed on the roadmap as *cannot be wired* — a screen
over this would render "Buyout — 0 packages · $0", which reads as *this project has no scope* rather
than *this input is in the other dialect*. **The capability was never missing.** Two halves of one
product simply never agreed on what to call a quantity, and nothing failed when they disagreed.

THE TRADE COMES FROM `classification.py`, NOT FROM A TABLE IN `procurement.py`. That spine already
maps IfcWall → ("04 20 00", "Unit Masonry"). A second mapping beside it is how two sources of truth
start disagreeing about what a wall is, so this asserts the value the spine returns rather than a
literal copied next to the engine.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_qto_trade.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_qto_trade.db"
os.environ["STORAGE_DIR"] = "./test_storage_qto_trade"
for _f in ("./test_qto_trade.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import classification, procurement  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


# Exactly what element_5d.py emits, key for key — not a convenient paraphrase of it. A fixture that
# invents its own shape would pass while the real caller kept failing, which is the defect this
# whole file exists because of.
MODEL_ROWS = [
    {"guid": "g1", "name": None, "ifc_class": "IfcWall", "storey": "L01",
     "basis": "area", "quantity": 1240.0, "rate": 85.0, "cost": 105400.0},
    {"guid": "g2", "name": None, "ifc_class": "IfcDoor", "storey": "L01",
     "basis": "count", "quantity": 42, "rate": 900.0, "cost": 37800.0},
    {"guid": "g3", "name": "Curtain wall CW-1", "ifc_class": "IfcCurtainWall", "storey": "L02",
     "basis": "area", "quantity": 610.0, "rate": 420.0, "cost": 256200.0},
    {"guid": "g4", "name": None, "ifc_class": "IfcSlab", "storey": "L02",
     "basis": "volume", "quantity": 310.0, "rate": 260.0, "cost": 80600.0},
]

out = procurement.buyout_packages(MODEL_ROWS)
pkgs = {p["package"]: p for p in out["packages"]}

check("a model-derived QTO produces real packages, not one 'General' bucket",
      out["package_count"] == 4 and "General" not in pkgs,
      f"{out['package_count']} package(s): {sorted(pkgs)}")

# THE MONEY IS THE POINT. package_count could be right while every est_cost was 0 — which is what
# would happen if `cost` were still read only under the hand-entered name.
check("...carrying the cost, not just the count",
      round(out["total_est_cost"]) == 480000,
      f"total_est_cost={out['total_est_cost']} (expected 480000)")

# The trade must equal what the SPINE says, looked up here rather than written as a literal.
for cls, qty in (("IfcWall", 1240.0), ("IfcDoor", 42), ("IfcCurtainWall", 610.0), ("IfcSlab", 310.0)):
    _, title = classification.classify(cls, "masterformat")
    p = pkgs.get(title)
    check(f"{cls} lands in the spine's trade ({title!r})", p is not None, f"packages: {sorted(pkgs)}")
    if p:
        check(f"...with {cls}'s quantity carried across",
              bool(p["lines"]) and p["lines"][0]["qty"] == qty,
              f"qty={p['lines'][0]['qty']} expected {qty}")

# An element with no name is identified by WHAT IT IS. Blank was the value that made it vanish.
wall = pkgs.get(classification.classify("IfcWall", "masterformat")[1])
check("an unnamed element still gets an item label", bool(wall and wall["lines"][0]["item"]),
      str(wall["lines"][0] if wall else None))
cw = pkgs.get(classification.classify("IfcCurtainWall", "masterformat")[1])
check("...and a NAMED element keeps its own name rather than the trade title",
      bool(cw) and cw["lines"][0]["item"] == "Curtain wall CW-1",
      str(cw["lines"][0] if cw else None))

# --------------------------------------------------------------------------------------------
# The hand-entered dialect must be untouched. This normaliser fills gaps; it must never override.
# --------------------------------------------------------------------------------------------
HAND = [{"item": "Cast-in-place slab", "trade": "Concrete", "qty": 300, "unit": "m3",
         "unit_price": 250.0, "cost": 75000.0}]
h = procurement.buyout_packages(HAND)
check("a hand-entered line still groups by its OWN trade, not a derived one",
      h["package_count"] == 1 and h["packages"][0]["package"] == "Concrete",
      str(h["packages"]))
check("...with its own item text and cost intact",
      bool(h["packages"]) and h["packages"][0]["lines"][0]["item"] == "Cast-in-place slab"
      and round(h["packages"][0]["est_cost"]) == 75000, str(h["packages"][0]))

# An explicit trade must WIN over the IFC class, or the spine would silently relabel a buyer's
# own packaging decision.
MIXED = [{"ifc_class": "IfcWall", "trade": "Sitework", "name": "Temp barrier",
          "quantity": 10, "rate": 5.0, "cost": 50.0}]
m = procurement.buyout_packages(MIXED)
# Indexed defensively ON PURPOSE. Under the pre-fix engine this list is EMPTY, and `m["packages"][0]`
# raised IndexError - which aborts the file and hides every assertion below it. A test that crashes
# instead of failing reports less the more broken the code is, which is exactly backwards.
check("an explicit trade beats the derived one",
      bool(m["packages"]) and m["packages"][0]["package"] == "Sitework", str(m["packages"]))

# --------------------------------------------------------------------------------------------
# A line that genuinely cannot be identified is REPORTED, not silently dropped.
# --------------------------------------------------------------------------------------------
noisy = procurement.buyout_packages([*MODEL_ROWS, {"nonsense": True}, {"guid": "x"}])
check("unidentifiable lines are counted on the response",
      noisy.get("skipped_unidentifiable") == 2, str(noisy.get("skipped_unidentifiable")))
check("...and do not reduce the real packages", noisy["package_count"] == 4,
      str(noisy["package_count"]))

# Empty in, honest out — and NOT a zero dressed as an answer.
empty = procurement.buyout_packages([])
check("no lines yields no packages and nothing skipped",
      empty["package_count"] == 0 and empty.get("skipped_unidentifiable") == 0, str(empty))

print(f"\ntest_qto_trade {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
