"""R22-OPTION-OBJECT — the basis rules, and the cases where the honest answer is "not priced".

The defect this module exists to prevent is not a wrong IRR. It is a **typed** IRR that renders
identically to a solved one, so a scheme gets chosen on a number nobody derived — the same shape as
the carbon basis on the option card and the promote in the equity waterfall.

Most of what is pinned here is therefore refusal: an option that names no scenario is NOT priced from
the project's other scenario, and a declared figure is never promoted to derived.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_option_economics.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import option_economics as oe  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def rec(name, **data):
    return {"id": name, "workflow_state": data.pop("state", "proposed"),
            "data": {"name": name, **data}}


class FakeScenario:
    """Stands in for models.Scenario — `_solved` only reads .result / .assumptions / .id / .name."""

    def __init__(self, sid, name, result=None, assumptions=None):
        self.id, self.name = sid, name
        self.result, self.assumptions = result, assumptions or {}


RESULT = {"sources_uses": {"total_uses": 11_233_324.77, "equity": 4_533_528.85,
                           "loan_amount": 6_699_796.33},
          "returns": {"equity_irr": 0.1974917423405669, "equity_multiple": 1.897,
                      "yield_on_cost": 0.0798}}

# --- 1. derived: the scenario is solved and the figures come from it -----------------------------------
sc = FakeScenario("s1", "Base case", result=RESULT)
d = oe.option_economics(rec("A", gross_area_sf=50_000, scenario="s1"), sc, [("s1", "Base case")])
check("a linked scenario yields a DERIVED basis", d["basis"] == oe.BASIS_DERIVED, d["basis"])
check("  hard_cost is the proforma's total uses", d["hard_cost"] == 11_233_324.77, d["hard_cost"])
check("  IRR is the equity IRR as a percentage, not a fraction", d["irr_pct"] == 19.75, d["irr_pct"])
check("  the equity and loan split comes through too",
      (d["equity"], d["loan_amount"]) == (4_533_528.85, 6_699_796.33), (d["equity"], d["loan_amount"]))
check("  cost per sf is derived from the solved cost",
      d["cost_per_sf"] == round(11_233_324.77 / 50_000, 2), d["cost_per_sf"])
check("  and the scenario is named, so the figure is traceable",
      (d["scenario_id"], d["scenario_name"]) == ("s1", "Base case"))

# --- 2. the disagreement — the thing this module exists to surface -------------------------------------
# A scheme whose typed IRR is well above what its own scenario solves to is the single most useful
# output here, and it is only visible because BOTH figures are kept.
agree = oe.option_economics(rec("B", scenario="s1", irr_pct=19.7), sc, [("s1", "Base case")])
check("a declared IRR matching the solved one is marked as agreeing",
      agree["agrees_with_declared"] is True, agree["agrees_with_declared"])
off = oe.option_economics(rec("C", scenario="s1", irr_pct=24.0), sc, [("s1", "Base case")])
check("a declared IRR 4 points above the solve is flagged as disagreeing",
      off["agrees_with_declared"] is False, off["agrees_with_declared"])
check("  and the delta is reported signed, so the direction is readable",
      off["declared_vs_derived_irr_pct"] == round(24.0 - 19.75, 2),
      off["declared_vs_derived_irr_pct"])
check("  the declared figure SURVIVES rather than being overwritten",
      off["declared_irr_pct"] == 24.0 and off["irr_pct"] == 19.75,
      (off["declared_irr_pct"], off["irr_pct"]))
check("  a rounded-but-close typed figure is not nagged about",
      oe.option_economics(rec("D", scenario="s1", irr_pct=20.0), sc,
                          [("s1", "x")])["agrees_with_declared"] is True)

# --- 3. UNLINKED — the refusal that matters most -------------------------------------------------------
# The project has a scenario; this option does not name it. Pricing it from that scenario anyway would
# invent provenance: it would assert that this massing was underwritten under that deal, which nobody
# recorded. That is the plausible-default failure, and it is refused.
un = oe.option_economics(rec("E", gross_area_sf=50_000), None, [("s1", "Base case")])
check("an option naming no scenario is NOT priced from the project's other scenario",
      un["irr_pct"] is None and un["hard_cost"] is None, (un["irr_pct"], un["hard_cost"]))
check("  its basis says 'unlinked', which is different from 'unavailable'",
      un["basis"] == oe.BASIS_UNLINKED, un["basis"])
check("  and the candidate scenario is named so the fix is one click",
      "Base case" in (un["note"] or ""), un["note"])
none_at_all = oe.option_economics(rec("F", gross_area_sf=50_000), None, [])
check("with no scenarios at all the basis is 'unavailable', not 'unlinked'",
      none_at_all["basis"] == oe.BASIS_UNAVAILABLE, none_at_all["basis"])
check("  the two reasons are different sentences", none_at_all["note"] != un["note"])

# --- 4. DECLARED is used and labelled, never promoted --------------------------------------------------
dec = oe.option_economics(rec("G", gross_area_sf=50_000, hard_cost=9_000_000, irr_pct=17.5), None, [])
check("hand-entered figures are used as given", (dec["hard_cost"], dec["irr_pct"]) == (9_000_000.0, 17.5))
check("  and labelled 'declared', never 'derived'", dec["basis"] == oe.BASIS_DECLARED, dec["basis"])
check("  the note says how to upgrade it", "link a proforma scenario" in (dec["note"] or ""))
check("  no solved-only fields are invented for it",
      dec["equity"] is None and dec["equity_multiple"] is None)

# --- 5. a scenario that will not solve reads as 'could not derive', never as zero ----------------------
# Renamed keys and dropped fields are a real state. The failure must not present as a free, zero-return
# scheme, which would win every ranking.
broken = FakeScenario("s2", "Broken", result=None, assumptions={"nonsense": True})
b = oe.option_economics(rec("H", scenario="s2", hard_cost=8_000_000), broken, [("s2", "Broken")])
check("an unsolvable scenario does not produce zeros", b["hard_cost"] == 8_000_000.0, b["hard_cost"])
check("  it falls back to the declared figures and says so",
      b["basis"] == oe.BASIS_DECLARED and "could not be solved" in (b["note"] or ""), b["note"])
b2 = oe.option_economics(rec("I", scenario="s2"), broken, [("s2", "Broken")])
check("  with nothing declared either, it is unavailable rather than 0",
      b2["irr_pct"] is None and b2["basis"] in (oe.BASIS_UNAVAILABLE, oe.BASIS_UNLINKED), b2["basis"])

# --- 6. bad data is absent, not favourable -------------------------------------------------------------
check("a non-numeric declared IRR is ignored rather than crashing",
      oe.option_economics(rec("J", irr_pct="about 20%"), None, [])["basis"] == oe.BASIS_UNAVAILABLE)
check("a currency-formatted cost is parsed",
      oe.option_economics(rec("K", hard_cost="$9,000,000"), None, [])["hard_cost"] == 9_000_000.0)

# --- 7. the roll-up ranks what it can and names what it cannot ------------------------------------------
rows = [rec("Priced", gross_area_sf=50_000, scenario="s1"),
        rec("Optimistic", gross_area_sf=50_000, scenario="s1", irr_pct=24.0),
        rec("Typed only", gross_area_sf=50_000, hard_cost=9_000_000, irr_pct=30.0),
        rec("Unlinked", gross_area_sf=50_000)]


class _FakeQuery:
    def __init__(self, items): self._items = items
    def filter(self, *a, **k): return self
    def all(self): return self._items


class _FakeDB:
    def query(self, *a, **k): return _FakeQuery([sc])


_orig_list, _orig_tables = oe.me.list_records, oe.me.TABLES
oe.me.list_records = lambda db, key, pid, limit=0: rows
oe.me.TABLES = {"design_option": object()}
try:
    R = oe.compare_economics(_FakeDB(), "p1")
finally:
    oe.me.list_records, oe.me.TABLES = _orig_list, _orig_tables

check("every option appears", R["count"] == 4, R["count"])
check("  two are derived from the scenario", R["derived_count"] == 2, R["derived_count"])
check("  three carry a figure, one does not",
      (R["priced_count"], R["unpriced_count"]) == (3, 1),
      (R["priced_count"], R["unpriced_count"]))
# 'Typed only' has the highest number (30%) but nobody solved it. It is ranked, because a declared
# figure IS a figure — but its basis is visible, which is the entire point.
check("the highest IRR wins the ranking even when it is only declared",
      R["best_irr"] == "Typed only", R["best_irr"])
check("  and that option's basis is visible as 'declared'",
      next(o for o in R["options"] if o["name"] == "Typed only")["basis"] == oe.BASIS_DECLARED)
check("the declared-vs-derived disagreement is surfaced as a named list",
      [x["name"] for x in R["declared_disagrees_with_derived"]] == ["Optimistic"],
      R["declared_disagrees_with_derived"])
check("  with both numbers and the delta",
      R["declared_disagrees_with_derived"][0]["declared_irr_pct"] == 24.0
      and R["declared_disagrees_with_derived"][0]["derived_irr_pct"] == 19.75,
      R["declared_disagrees_with_derived"])
check("the unlinked option is listed, not dropped",
      any(o["name"] == "Unlinked" and o["basis"] == oe.BASIS_UNLINKED for o in R["options"]))
check("the project's scenarios are named so an option can be linked",
      R["scenarios"] == [{"id": "s1", "name": "Base case"}], R["scenarios"])

# scenarios can be referenced by NAME as well as id — a text field is what a person types into
oe.me.list_records = lambda db, key, pid, limit=0: [rec("ByName", scenario="base case")]
oe.me.TABLES = {"design_option": object()}
try:
    N = oe.compare_economics(_FakeDB(), "p1")
finally:
    oe.me.list_records, oe.me.TABLES = _orig_list, _orig_tables
check("a scenario referenced by NAME resolves too (case-insensitively)",
      N["options"][0]["basis"] == oe.BASIS_DERIVED, N["options"][0]["basis"])

print()
if FAILED:
    print(f"option_economics: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("option_economics: all checks passed")
