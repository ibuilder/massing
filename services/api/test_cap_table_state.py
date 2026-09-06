"""Only COMMITTED capital owns anything — and a default state is not a signal.

`cap_table` summed `commitment` across every investor whatever their workflow state. The roadmap
measured it: two funded LPs at $6M and $4M plus one `prospect` carrying a $10M interest and $0
contributed, and the prospect took 50% of the table, halved Anchor LP from 60% to 30%, and sorted to
the top as the largest apparent owner. It did not stop at display — `distwaterfall` allocates
`share = lp_total * (commitment / lp_commit)` off these rows, so the prospect drew real money.

THE OBVIOUS FIX IS WRONG ON ITS OWN, which is why this file exists rather than a one-line filter.
`investor` declares `initial: prospect` and every record is stamped with it at creation, so on a
project where nobody ran the `commit` transition EVERY investor is a prospect and a filter empties
the cap table. The roadmap records that this is not hypothetical: it was implemented, and
`test_distwaterfall` — which builds three investors through the real API and expects a $2,000,000
distribution — returned 0.0. `workflow_in_use` is the distinction that makes the filter safe.

Run: PYTHONPATH=src ./.venv/bin/python test_cap_table_state.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_cap_table_state.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_test_cap_table_state")
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_cap_table_state.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.capital import cap_table  # noqa: E402
from aec_api.main import app  # noqa: E402

FUNDED, PROSPECT, COMMITTED, EXITED = "funded", "prospect", "committed", "exited"


def _inv(n, state, commit, contributed=0.0, cls="LP"):
    return {"id": n, "ref": n, "workflow_state": state,
            "data": {"investor": n, "investor_class": cls,
                     "commitment": commit, "contributed": contributed}}


# --- the roadmap's own measured scenario, number for number -------------------------------------
ct = cap_table([_inv("Anchor LP", FUNDED, 6_000_000, 6_000_000),
                _inv("Second LP", FUNDED, 4_000_000, 4_000_000),
                _inv("Maybe LP", PROSPECT, 10_000_000, 0)])
by = {r["investor"]: r for r in ct["rows"]}
assert by["Anchor LP"]["ownership_pct"] == 60.0, by["Anchor LP"]      # was 30.0
assert by["Second LP"]["ownership_pct"] == 40.0, by["Second LP"]      # was 20.0
assert by["Maybe LP"]["ownership_pct"] == 0.0, by["Maybe LP"]         # was 50.0
assert ct["total_commitment"] == 10_000_000.0, ct["total_commitment"]

# the prospect is NOT dropped — its money is reported, just not as ownership. Deleting the row would
# hide a real pipeline; counting it as ownership was the bug.
assert by["Maybe LP"]["commitment"] == 10_000_000.0
assert ct["pipeline_commitment"] == 10_000_000.0, ct["pipeline_commitment"]

# and it no longer sorts to the top as the largest apparent owner: rank is read as ownership.
assert [r["investor"] for r in ct["rows"]] == ["Anchor LP", "Second LP", "Maybe LP"], ct["rows"]

# by_class must agree with the denominator, or the two halves of the same table contradict.
assert sum(ct["by_class"].values()) == ct["total_commitment"], ct["by_class"]

# --- THE TRAP: every investor still sits at the stamped initial state ---------------------------
# This is the case that broke the naive filter. `prospect` here means "nobody used the workflow",
# not "not committed", so the table must behave exactly as it did before.
allp = cap_table([_inv("A", PROSPECT, 1_000_000), _inv("B", PROSPECT, 1_000_000),
                  _inv("C", PROSPECT, 1_000_000)])
assert allp["workflow_in_use"] is False, allp["workflow_in_use"]
assert allp["total_commitment"] == 3_000_000.0, allp["total_commitment"]
assert {round(r["ownership_pct"], 2) for r in allp["rows"]} == {33.33}, allp["rows"]
assert allp["pipeline_commitment"] == 0.0, "nothing is pipeline when nothing is committed yet"

# ONE investor moving off the initial state flips the reading for the whole project — that is the
# signal, and it is a project-level fact, not a per-row one.
mixed = cap_table([_inv("A", COMMITTED, 1_000_000), _inv("B", PROSPECT, 1_000_000),
                   _inv("C", PROSPECT, 1_000_000)])
assert mixed["workflow_in_use"] is True
assert mixed["total_commitment"] == 1_000_000.0, mixed["total_commitment"]
assert mixed["pipeline_commitment"] == 2_000_000.0, mixed["pipeline_commitment"]

# --- `exited` is evidence the workflow was used, but is not current ownership -------------------
# An investor who has left does not hold a share; their presence still proves the workflow is live.
ex = cap_table([_inv("Gone", EXITED, 5_000_000, 5_000_000), _inv("Here", PROSPECT, 5_000_000)])
assert ex["workflow_in_use"] is True, "an exited investor proves the workflow was used"
assert {r["investor"]: r["counts_toward_ownership"] for r in ex["rows"]} == {
    "Gone": False, "Here": False}, ex["rows"]

# --- the decision travels ON THE ROW, so seven consumers cannot disagree ------------------------
for r in ct["rows"]:
    assert "counts_toward_ownership" in r, r
assert [r["counts_toward_ownership"] for r in ct["rows"]] == [True, True, False]

# --- and the money follows: a prospect must draw NO distribution ---------------------------------
# Mutation-checking exposed that `test_distwaterfall` passes even when `distwaterfall` ignores the
# flag — its fixture has no prospect, so the filter was unexercised. This is that missing case, built
# through the real API so the records carry the workflow's own stamped initial state.
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Waterfall states"}).json()["id"]

    def _mk(name, cls, commit, state=None):
        rid = c.post(f"/projects/{pid}/modules/investor",
                     json={"data": {"investor": name, "investor_class": cls,
                                    "commitment": commit}}).json()["id"]
        if state:
            c.post(f"/projects/{pid}/modules/investor/{rid}/transition",
                   json={"action": state})
        return rid

    _mk("Alpha LP", "LP", 900_000, "commit")     # prospect -> committed
    _mk("GP Co", "GP", 100_000, "commit")
    _mk("Maybe LP", "LP", 9_000_000)             # left at the stamped initial state

    w = c.post(f"/projects/{pid}/waterfall", json={"exit_amount": 2_000_000}).json()
    per = {x["investor"]: x["distribution"] for x in w["per_investor"]}
    assert "Maybe LP" not in per or per["Maybe LP"] == 0.0, per
    # Alpha holds the whole LP class despite being outweighed 10:1 by an uncommitted interest.
    assert per.get("Alpha LP", 0) > 0, per
    assert round(sum(per.values()), 2) == round(w["total_distributable"], 2), (per, w)

print("test_cap_table_state OK")
