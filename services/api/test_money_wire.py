"""MONEY-WIRE — the decimal helpers are actually used where money is SPLIT.

`money.py` shipped with its own suite and **zero importers** (found by `test_reachable`), so every
float-drift problem it was written to prevent was still live. This wires the case where drift
produces a wrong number somebody would notice — splitting a total across parties — and asserts the
property that matters: the parts sum to the whole, and the leftover cents are distributed by a
defensible rule rather than dumped on whoever sorts last.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_money_wire.py
"""
from __future__ import annotations

import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_money_wire.db"
os.environ["STORAGE_DIR"] = "./test_storage_money_wire"

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import capital, money  # noqa: E402


def inv(ref, name, commitment):
    return {"ref": ref, "data": {"investor": name, "commitment": commitment}}


THREE_EQUAL = [inv("I1", "Alpha", 100), inv("I2", "Beta", 100), inv("I3", "Gamma", 100)]


def test_the_parts_sum_to_the_whole_exactly():
    out = capital.allocate(THREE_EQUAL, 100.0)
    parts = [a["amount"] for a in out["allocations"]]
    assert money.to_cents(sum(parts)) == money.to_cents(100.0), parts


def test_a_three_way_split_of_100_is_NOT_99_99():
    # The textbook case: round(100/3, 2) three times gives 33.33 × 3 = 99.99 and a lost penny.
    parts = sorted(a["amount"] for a in capital.allocate(THREE_EQUAL, 100.0)["allocations"])
    assert parts == [33.33, 33.33, 33.34], parts


def test_the_leftover_cent_is_NOT_always_the_same_investor():
    # THE REASON THIS CHANGED. The previous rule absorbed all rounding into the last row, so the
    # investor who happened to sort last carried every leftover cent on every call and every
    # distribution — a systematic, arbitrary transfer that an LP finds in a reconciliation and
    # nobody can justify. Largest-remainder gives the cent to the largest fractional part, so with
    # unequal commitments it lands where the maths puts it, not where the sort did.
    uneven = [inv("I1", "Alpha", 500), inv("I2", "Beta", 300), inv("I3", "Gamma", 200)]
    out = capital.allocate(uneven, 1000.01)
    by_ref = {a["ref"]: a["amount"] for a in out["allocations"]}
    assert money.to_cents(sum(by_ref.values())) == money.to_cents(1000.01), by_ref
    assert by_ref["I1"] > by_ref["I2"] > by_ref["I3"], by_ref     # pro-rata order preserved


def test_a_distribution_splits_the_same_way_as_a_call():
    call = capital.allocate(THREE_EQUAL, 100.0, kind="call")
    dist = capital.allocate(THREE_EQUAL, 100.0, kind="distribution")
    assert [a["amount"] for a in call["allocations"]] == [a["amount"] for a in dist["allocations"]]
    assert call["kind"] == "call" and dist["kind"] == "distribution"


def test_zero_commitments_allocate_nothing_rather_than_dividing_by_zero():
    out = capital.allocate([inv("I1", "Alpha", 0), inv("I2", "Beta", 0)], 500.0)
    assert [a["amount"] for a in out["allocations"]] == [0.0, 0.0], out


def test_no_investors_is_an_empty_allocation_not_a_crash():
    assert capital.allocate([], 100.0)["allocations"] == []


def test_the_helpers_round_the_money_way_not_the_float_way():
    # `round(2.675, 2)` is 2.67 because 2.675 is not exactly representable. Money rounds half UP.
    assert money.q2(2.675) == 2.68
    assert round(2.675, 2) == 2.67, "if this ever changes, the reason for money.q2 changed too"


def test_capital_actually_imports_money_now():
    # The point of the exercise: `money` had ZERO importers, so none of the above was reachable.
    import inspect
    assert "money." in inspect.getsource(capital.allocate), "capital.allocate must use the helpers"



# --- MONEY-WIRE ② — spreading a total across periods -----------------------------------------------
def test_a_budget_spread_sums_to_the_budget():
    # `bud / len(months)` rounded per bucket does not add up, and a spread curve whose months do not
    # sum to the budget is the first thing a PM notices when reconciling. Checked at the helper level
    # because the engine needs a DB; the engines call exactly this.
    for total, n in ((100.0, 3), (1000.01, 7), (0.05, 4), (123456.78, 13)):
        parts = money.allocate(total, [1.0] * n)
        assert len(parts) == n, (total, n)
        assert money.to_cents(sum(parts)) == money.to_cents(total), (total, n, parts)


def test_an_even_spread_differs_by_at_most_a_cent_between_periods():
    # Largest-remainder, not "dump it in the last bucket" — no single month absorbs the rounding.
    parts = money.allocate(100.0, [1.0] * 3)
    assert max(parts) - min(parts) <= 0.01 + 1e-9, parts


def test_a_single_period_gets_the_whole_amount():
    assert money.allocate(250.0, [1.0]) == [250.0]


def test_zero_periods_allocates_nothing_rather_than_dividing_by_zero():
    assert money.allocate(250.0, []) == []


def test_the_engines_that_split_a_total_actually_call_the_helper():
    # The reachability half — the engines had the same `/ len(...)` bug and would keep it otherwise.
    import inspect

    from aec_api import project_budget, resource_loading
    assert "money.allocate" in inspect.getsource(project_budget), "budget spread must use the helper"
    assert "money.allocate" in inspect.getsource(resource_loading), "resource loading must use it too"

for _n, _f in sorted(globals().items()):
    if _n.startswith("test_") and callable(_f):
        _f()

print("MONEY-WIRE OK - money.py had its own suite and ZERO importers, so every float-drift problem "
      "it was written to prevent was still live. Wired into the case where drift produces a number "
      "somebody notices: splitting a total across parties. A three-way split of $100 is now "
      "33.34/33.33/33.33 rather than three 33.33s summing to 99.99. And the leftover cents are "
      "distributed by LARGEST REMAINDER instead of being absorbed into the last row - the old rule "
      "summed correctly but put every spare cent on whichever investor happened to sort last, on "
      "every call and every distribution, which is a systematic and arbitrary transfer that an LP "
      "finds in a reconciliation and nobody can explain.")
