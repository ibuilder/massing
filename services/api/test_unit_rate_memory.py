"""R22-MEMORY ② — the unit rate has to be a distribution over PROJECTS, not a blended average.

Every number here is hand-computed and asserted exactly. The finance-math review of this repo found
17 defects in a package whose tests RANGE-checked — `0 <= p <= 1` is satisfied by the right answer
and the wrong one equally — so "the median is a number between low and high" is not a test.

The three that would each produce a plausible wrong figure:

* pooling `Σcost ÷ Σquantity` and calling it the median (one large project sets it, and the spread
  is invented rather than observed);
* summing quantities across DIFFERENT units for one cost code;
* dropping a project that has cost but no quantity, so an unmeasurable job silently reads as absent
  rather than as excluded.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_unit_rate_memory.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import unit_rate_memory as urm  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def cost(pid, code, amount):
    return (pid, {"cost_code": code, "amount": amount})


def qty(pid, code, quantity, unit):
    return (pid, {"cost_code": code, "quantity": quantity, "unit": unit})


# --- 1. the arithmetic, hand-computed ---------------------------------------------------------------
# P1: 03 30 00 — $60,000 over 200 m3 -> 300.00 /m3
# P2: 03 30 00 — $22,000 over 100 m3 -> 220.00 /m3
# P3: 03 30 00 — $90,000 over 200 m3 -> 450.00 /m3
COSTS = [cost("P1", "03 30 00", 40_000), cost("P1", "03 30 00", 20_000),
         cost("P2", "03 30 00", 22_000),
         cost("P3", "03 30 00", 90_000)]
QTYS = [qty("P1", "03 30 00", 150, "m3"), qty("P1", "03 30 00", 50, "m3"),
        qty("P2", "03 30 00", 100, "m3"),
        qty("P3", "03 30 00", 200, "m3")]

j = urm.per_project_rates(COSTS, QTYS)
by_pid = {r["project_id"]: r for r in j["rates"]}
check("a project's rows are summed before dividing",
      by_pid["P1"]["cost"] == 60_000.0 and by_pid["P1"]["quantity"] == 200.0)
check("P1 rate = 60000 / 200 = 300.0", by_pid["P1"]["rate"] == 300.0, by_pid["P1"]["rate"])
check("P2 rate = 22000 / 100 = 220.0", by_pid["P2"]["rate"] == 220.0, by_pid["P2"]["rate"])
check("P3 rate = 90000 / 200 = 450.0", by_pid["P3"]["rate"] == 450.0, by_pid["P3"]["rate"])
check("the unit rides with the rate", {r["unit"] for r in j["rates"]} == {"m3"})

# --- 2. the distribution is over PROJECTS, and pooling is a different number -------------------------
s = urm.summarise(j["rates"], min_projects=3)
check("one (code, unit) group", len(s) == 1, [(c["cost_code"], c["unit"]) for c in s])
g = s[0]
check("three projects in the population", g["projects"] == 3)
check("median of {220, 300, 450} is 300.0 — the middle PROJECT",
      g["median"] == 300.0, g["median"])
check("low is 220.0 and high is 450.0", g["low"] == 220.0 and g["high"] == 450.0)

# THE assertion this module exists for. Pooled = 172000/500 = 344.0, which is NOT the median 300.0.
# If someone "simplifies" summarise() to sum-then-divide, median silently becomes 344.0 and every
# range check still passes.
check("pooled_rate = 172000 / 500 = 344.0", g["pooled_rate"] == 344.0, g["pooled_rate"])
check("  and it DIFFERS from the median — pooling is not the distribution",
      g["pooled_rate"] != g["median"], (g["pooled_rate"], g["median"]))
check("totals are reported so the pooled figure can be rechecked",
      g["total_cost"] == 172_000.0 and g["total_quantity"] == 500.0)
check("spread_ratio = 450 / 220 = 2.05", g["spread_ratio"] == 2.05, g["spread_ratio"])
check("per_project rows ride along, sorted by rate",
      [r["rate"] for r in g["per_project"]] == [220.0, 300.0, 450.0])
check("three projects meets the default threshold", g["below_threshold"] is False)
check("two would not", urm.summarise(j["rates"][:2], min_projects=3)[0]["below_threshold"] is True)

# --- 3. units are grouped, never converted -----------------------------------------------------------
MIXED = [cost("A", "09 21 16", 1_000), cost("B", "09 21 16", 2_000)]
MIXEDQ = [qty("A", "09 21 16", 100, "m2"), qty("B", "09 21 16", 100, "SF")]
m = urm.summarise(urm.per_project_rates(MIXED, MIXEDQ)["rates"], min_projects=1)
check("m2 and SF are TWO populations, not one", len(m) == 2, [(c["cost_code"], c["unit"]) for c in m])
check("  neither is converted into the other",
      {c["unit"] for c in m} == {"m2", "sf"}, [c["unit"] for c in m])
check("  each keeps its own rate", sorted(c["median"] for c in m) == [10.0, 20.0])

# One project recording ONE code under TWO units cannot be attributed, so it is excluded — not
# summed across units, which would produce a rate in a unit that does not exist.
AMB = urm.per_project_rates([cost("X", "03 30 00", 5_000)],
                            [qty("X", "03 30 00", 50, "m3"), qty("X", "03 30 00", 100, "SF")])
check("a project mixing units within one code produces NO rate", AMB["rates"] == [])
check("  and is reported as excluded with both units named",
      len(AMB["excluded"]["mixed_units"]) == 1
      and AMB["excluded"]["mixed_units"][0]["units"] == ["m3", "sf"],
      AMB["excluded"]["mixed_units"])
check("  with a reason that says why splitting would be a guess",
      "guess" in AMB["excluded"]["mixed_units"][0]["reason"])

# --- 4. unmeasurable is not zero ---------------------------------------------------------------------
E = urm.per_project_rates(
    [cost("C1", "05 12 00", 8_000), cost("C2", "05 12 00", 4_000)],
    [qty("C2", "05 12 00", 40, "t"), qty("C3", "05 12 00", 10, "t")])
check("a project with cost but no quantity yields no rate",
      [r["project_id"] for r in E["rates"]] == ["C2"])
check("  it is reported, not dropped",
      [x["project_id"] for x in E["excluded"]["cost_without_quantity"]] == ["C1"])
check("  with its cost, so the gap is quantifiable",
      E["excluded"]["cost_without_quantity"][0]["cost"] == 8_000.0)
check("a project with quantity but no cost is reported too",
      [x["project_id"] for x in E["excluded"]["quantity_without_cost"]] == ["C3"])
check("the measurable one is still correct: 4000 / 40 = 100.0",
      E["rates"][0]["rate"] == 100.0, E["rates"][0]["rate"])
check("excluded rows carry the never-dropped note", "not a project that cost zero"
      in E["excluded"]["note"])

# --- 5. degenerate inputs ------------------------------------------------------------------------------
check("no records at all is empty, not an error",
      urm.per_project_rates([], [])["rates"] == [])
check("a zero quantity does not divide by zero",
      urm.per_project_rates([cost("Z", "x", 100)], [qty("Z", "x", 0, "m")])["rates"] == [])
check("  and the zero-quantity project is reported as cost-without-quantity",
      [x["project_id"] for x in urm.per_project_rates(
          [cost("Z", "x", 100)], [qty("Z", "x", 0, "m")])["excluded"]["cost_without_quantity"]] == ["Z"])
check("a non-numeric amount is ignored rather than crashing",
      urm.per_project_rates([cost("Z", "x", "abc")], [qty("Z", "x", 5, "m")])["rates"] == [])
check("an uncoded row is ignored",
      urm.per_project_rates([cost("Z", "", 100)], [qty("Z", "", 5, "m")])["rates"] == [])
check("whitespace in a code is normalised so ' 03 30 00 ' joins '03 30 00'",
      urm.per_project_rates([cost("W", " 03 30 00 ", 100)],
                            [qty("W", "03 30 00", 5, "m3")])["rates"][0]["rate"] == 20.0)
check("unit case is normalised so M3 and m3 are one population",
      len(urm.summarise(urm.per_project_rates(
          [cost("A", "c", 100), cost("B", "c", 200)],
          [qty("A", "c", 10, "M3"), qty("B", "c", 10, "m3")])["rates"], 1)) == 1)

# --- 6. the percentile method matches benchmarking's ----------------------------------------------------
from aec_api import benchmarking  # noqa: E402

vals = [1.0, 2.0, 3.0, 4.0]
check("percentiles agree with benchmarking's, so a cost p75 and a rate p75 are comparable",
      all(urm._pctile(vals, q) == benchmarking._pctile(vals, q) for q in (0.0, 0.25, 0.5, 0.75, 1.0)))

# --- 7. the totals honour the formula the payload states ----------------------------------------------
# `unit_rates()` tells the reader `pooled_rate` is Σcost ÷ Σquantity. It was not: `summarise()` summed
# the per-project `cost`/`quantity` fields, which `per_project_rates()` had already rounded for display.
# At 60 projects the reported total was 6000.00 against a true 6000.30 and the pooled rate was 33.3333
# against a true 33.3344 — small, plausible, and contradicting the definition printed beside it. That is
# the failure mode worth a test: not a number that is missing, a number that disagrees with its own
# stated basis. Anyone re-deriving the total from `per_project` gets a different answer and has no way
# to tell which is wrong.
N, AMT, QTY = 60, 100.005, 3.00005
drift = urm.summarise(urm.per_project_rates(
    [cost(f"P{i}", "C", AMT) for i in range(N)],
    [qty(f"P{i}", "C", QTY, "m") for i in range(N)])["rates"], 1)[0]
raw_cost, raw_qty = AMT * N, QTY * N
check("total_cost is the sum of RAW costs, not of rounded ones",
      drift["total_cost"] == round(raw_cost, 2), (drift["total_cost"], round(raw_cost, 2)))
check("total_quantity likewise", drift["total_quantity"] == round(raw_qty, 4),
      (drift["total_quantity"], round(raw_qty, 4)))
check("pooled_rate equals the Sum(cost)/Sum(quantity) the payload claims it is",
      drift["pooled_rate"] == round(raw_cost / raw_qty, 4),
      (drift["pooled_rate"], round(raw_cost / raw_qty, 4)))
# The rounded per-project values must still be what a reader sees, and the raw carrier must not leak.
check("the published per-project rows keep their rounded display values",
      drift["per_project"][0]["cost"] == round(AMT, 2))
check("and no internal raw carrier is exposed in the payload",
      all("_raw" not in r for r in drift["per_project"]), drift["per_project"][0].keys())

print()
if FAILED:
    print(f"unit_rate_memory: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("unit_rate_memory: all checks passed")
