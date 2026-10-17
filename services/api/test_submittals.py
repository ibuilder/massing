"""SUBMITTAL-RETURNED — a rejected submittal six weeks late read as closed, and two counts hid
their populations.

`submittals.CLOSED_STATES` was hand-written as `("returned", "closed")`. `returned` is NOT a
terminal state: the shipped `submittal` workflow gives it two outgoing transitions, `close` and
`revise_resubmit`. So a submittal the A/E sent back marked *"Revise & Resubmit"* was counted as
closed -- out of `open_count`, and unable to be overdue at all, because `is_overdue` tested
`st not in CLOSED_STATES`.

Three things are asserted here and they are the whole point:

**1. The derivation reproduces the sibling register's hand-written list and contradicts this one.**
`terminal_states` is "a state no transition leaves". Against `rfi/module.json` it returns exactly
`rfi.CLOSED_STATES` -- a tuple written out by hand, in another file, and right. Against
`submittal/module.json` it returns `("closed",)` alone. *Two siblings hardcoded the same kind of
list; the rule says which one drifted*, and that is the argument for deriving it rather than
fixing the literal.

**2. A rejected submittal is open, overdue, and distinguishable from an approved one.** Approved and
Revise & Resubmit agree on `open_count` and `overdue_count` -- both are `returned`, both are past
their date -- so `needs_resubmittal_count` is what separates them. *The states say where the record
is; the disposition says which way it is going.*

**3. Each count states its population.** `overdue_count` can only count a submittal carrying a
`required_on_site` date, and `avg_turnaround_days` only one carrying both review dates. A register
with neither recorded reported `0 overdue` and `null` turnaround, which reads as a clean log.
"""
import json
import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///./test_submittals.db"
os.environ["STORAGE_DIR"] = "./test_storage_submittals"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_submittals.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import rfi  # noqa: E402
from aec_api import submittals as S  # noqa: E402

TODAY = date(2026, 10, 17)
HERE = os.path.dirname(os.path.abspath(__file__))


def _mod(key: str) -> dict:
    with open(os.path.join(HERE, "modules", key, "module.json"), encoding="utf-8") as fh:
        return json.load(fh)


def sub(ref, st, **d):
    return {"ref": ref, "workflow_state": st, "data": d}


# --- 1. the derivation, against both shipped workflows ------------------------------------------
rfi_mod, sub_mod = _mod("rfi"), _mod("submittal")
# `returned` HAS outgoing transitions, which is the fact the old literal denied.
_out = {str(t["from"]) for t in sub_mod["workflow"]["transitions"] if t.get("from")}
assert "returned" in _out, sub_mod["workflow"]["transitions"]
assert {"close", "revise_resubmit"} <= {
    str(t["action"]) for t in sub_mod["workflow"]["transitions"] if t.get("from") == "returned"
}, "the two transitions that make `returned` non-terminal"

# It reproduces the SIBLING's hand-written tuple exactly. This is the check that the rule is the
# right rule: `rfi.CLOSED_STATES` was written by hand in another module and is correct.
assert S.terminal_states(rfi_mod) == sorted(rfi.CLOSED_STATES), (
    S.terminal_states(rfi_mod), rfi.CLOSED_STATES)
# ...and it disagrees with the one that drifted, which now matches it.
assert S.terminal_states(sub_mod) == ["closed"], S.terminal_states(sub_mod)
assert sorted(S.CLOSED_STATES) == S.terminal_states(sub_mod), S.CLOSED_STATES
assert "returned" not in S.CLOSED_STATES, S.CLOSED_STATES

# A state with no declared transitions at all is terminal; an empty workflow has no states to rule
# on, which is not the same as "every state is terminal".
assert S.terminal_states({"workflow": {"states": ["a", "b"], "transitions": [
    {"from": "a", "to": "b", "action": "go"}]}}) == ["b"]
assert S.terminal_states({}) == []
assert S.terminal_states({"workflow": {"states": ["a"], "transitions": []}}) == ["a"]

# --- 2. a rejected submittal is open, overdue, and distinguishable -----------------------------
_dates = {"spec_section": "08 44 13", "required_on_site": "2026-09-01",
          "date_received": "2026-08-01", "date_returned": "2026-08-10"}
CLOSED = S.terminal_states(sub_mod)
rej = S.register([sub("S-001", "returned", title="CW shop dwgs",
                      disposition="Revise & Resubmit", **_dates)], as_of=TODAY, closed=CLOSED)
app = S.register([sub("S-002", "returned", title="CW shop dwgs",
                      disposition="Approved", **_dates)], as_of=TODAY, closed=CLOSED)

# THE DEFECT: before this item both of these were 0, on a row six weeks past its required-on-site
# date -- `returned` was in CLOSED_STATES, so the row was neither open nor capable of being late.
assert (rej["open_count"], rej["overdue_count"]) == (1, 1), rej
assert rej["rows"][0]["overdue"] is True, rej["rows"][0]
assert rej["rows"][0]["needs_resubmittal"] is True, rej["rows"][0]

# The two agree on open and overdue -- both `returned`, both late -- so the resubmittal count is
# what tells them apart. A state says where the record IS; the disposition says where it is GOING.
assert (app["open_count"], app["overdue_count"]) == (rej["open_count"], rej["overdue_count"]), (app, rej)
assert app["avg_turnaround_days"] == rej["avg_turnaround_days"] == 9.0, (app, rej)
assert app["needs_resubmittal_count"] == 0 and rej["needs_resubmittal_count"] == 1, (app, rej)
assert app["coverage_note"] != rej["coverage_note"], app["coverage_note"]
assert "resubmittal" in rej["coverage_note"], rej["coverage_note"]

# A CLOSED submittal is not awaiting a resubmittal however it was dispositioned -- the flag is about
# work still owed, not about what the A/E wrote.
done = S.register([sub("S-003", "closed", disposition="Rejected", **_dates)],
                  as_of=TODAY, closed=CLOSED)
assert (done["open_count"], done["overdue_count"], done["needs_resubmittal_count"]) == (0, 0, 0), done
assert done["rows"][0]["closed"] is True, done["rows"][0]

# `Rejected` counts as well as `Revise & Resubmit` -- both send it back.
for disp in S.RESUBMIT_DISPOSITIONS:
    one = S.register([sub("S-9", "returned", disposition=disp, **_dates)], as_of=TODAY, closed=CLOSED)
    assert one["needs_resubmittal_count"] == 1, (disp, one)
# ...and an accepting disposition does not.
for disp in ("Approved", "Approved as Noted", "For Record Only", None):
    one = S.register([sub("S-9", "returned", disposition=disp, **_dates)], as_of=TODAY, closed=CLOSED)
    assert one["needs_resubmittal_count"] == 0, (disp, one)

# --- 3. each count states the population it is over --------------------------------------------
undated = S.register([sub(f"S-{i:03d}", "ae_review", spec_section="09") for i in range(40)],
                     as_of=TODAY, closed=CLOSED)
# 40 submittals in review and `overdue_count` is 0 -- which reads as "nothing is late" and is
# really "nothing can be measured". EXPIRY-UNDATED, one register over.
assert (undated["overdue_count"], undated["dated_count"], undated["undated_count"]) == (0, 0, 40), undated
assert undated["avg_turnaround_days"] is None and undated["turnaround_count"] == 0, undated
assert "0 of 40 carrying a required-on-site date" in undated["coverage_note"], undated["coverage_note"]
assert "40 have none" in undated["coverage_note"], undated["coverage_note"]

# An average over 2 of 40 and one over 2 of 2 are the same number; `turnaround_count` is the
# difference, and before this item the response carried only the number.
thin = S.register(
    [sub(f"S-{i:03d}", "ae_review", spec_section="09") for i in range(38)]
    + [sub("S-900", "closed", spec_section="09", date_received="2026-08-01", date_returned="2026-08-04"),
       sub("S-901", "closed", spec_section="09", date_received="2026-08-01", date_returned="2026-08-05")],
    as_of=TODAY, closed=CLOSED)
whole = S.register(
    [sub("S-900", "closed", spec_section="09", date_received="2026-08-01", date_returned="2026-08-04"),
     sub("S-901", "closed", spec_section="09", date_received="2026-08-01", date_returned="2026-08-05")],
    as_of=TODAY, closed=CLOSED)
assert thin["avg_turnaround_days"] == whole["avg_turnaround_days"] == 3.5, (thin, whole)
assert thin["turnaround_count"] == whole["turnaround_count"] == 2, (thin, whole)
assert thin["submittal_count"] == 40 and whole["submittal_count"] == 2, (thin, whole)
assert thin["coverage_note"] != whole["coverage_note"], thin["coverage_note"]
assert "2 of 40" in thin["coverage_note"], thin["coverage_note"]

# A fully-dated, nothing-owed register claims nothing outside its counts.
clean = S.register([sub("S-1", "closed", disposition="Approved", **_dates)], as_of=TODAY, closed=CLOSED)
assert "carries the dates both counts need" in clean["coverage_note"], clean["coverage_note"]
assert S.register([], as_of=TODAY)["coverage_note"] == "No submittals in the register.", "empty"

# `overdue_assessed` is the per-row form: `overdue: False` means two different things.
rows = S.register([sub("A", "ae_review", spec_section="09"),
                   sub("B", "ae_review", spec_section="09", required_on_site="2030-01-01")],
                  as_of=TODAY, closed=CLOSED)["rows"]
by_ref = {r["ref"]: r for r in rows}
assert by_ref["A"]["overdue"] is False and by_ref["A"]["overdue_assessed"] is False, by_ref["A"]
assert by_ref["B"]["overdue"] is False and by_ref["B"]["overdue_assessed"] is True, by_ref["B"]

# --- the workflow in force, not the shipped one -------------------------------------------------
# WORKFLOW-DARK: a project may replace these transitions, so the set is resolved per project and
# stated on the wire. `None` from `effective_closed` means the question could not be answered.
assert S.register([], closed=["x"])["closed_states"] == ["x"]
assert S.register([], closed=["x"], overridden=True)["workflow_overridden"] is True
assert S.register([])["closed_states"] == list(S.CLOSED_STATES), "the shipped fallback"
import aec_api.modules_registry as MR  # noqa: E402

_kept = MR.REGISTRY.pop("submittal", None)
try:
    assert S.effective_closed("nope") == (None, False), "module absent -> the question is unanswered"
finally:
    if _kept is not None:
        MR.REGISTRY["submittal"] = _kept
MR.load_registry()
_eff, _over = S.effective_closed("no-such-project")
assert _eff == ["closed"] and _over is False, (_eff, _over)

# --- the two server-side consumers that quote these counts --------------------------------------
# The health tile is checked BEHAVIOURALLY, and that is the lesson of this block. The first version
# of this fix put the verdict inline in `project_health` and asserted the keys appeared in the file;
# the mutation reverting the verdict to `overdue_count` alone stayed GREEN, because the HEADLINE
# reads the same keys. *Reading a value and ruling on it are two different questions, and a
# substring over the file cannot tell them apart.* `submittal_status` is a function now, so a
# mutation has somewhere to land.
from aec_api.projecthealth import submittal_headline, submittal_status  # noqa: E402

assert submittal_status(rej) == "amber", "a rejected row six weeks late left the tile green"
assert submittal_status(done) == "green", done
assert submittal_status(undated) == "amber", "an open register nothing can assess read as on-time"
# ...and a partly-dated register is NOT amber for that reason alone: most logs are partly dated,
# and a warning on every one of them is a warning nobody reads.
_partly = S.register([sub("A", "ae_review", spec_section="09"),
                      sub("B", "ae_review", spec_section="09", required_on_site="2030-01-01")],
                     as_of=TODAY, closed=CLOSED)
assert submittal_status(_partly) == "green", _partly
assert submittal_status(S.register([], as_of=TODAY)) == "green", "an empty register is not a finding"
# Six rejected rows is red on the resubmittal arm alone, with nothing overdue.
_many = S.register([sub(f"R{i}", "returned", spec_section="09", disposition="Rejected")
                    for i in range(6)], as_of=TODAY, closed=CLOSED)
assert _many["overdue_count"] == 0 and submittal_status(_many) == "red", _many
assert "6 awaiting resubmittal" in submittal_headline(_many), submittal_headline(_many)
assert "not assessable for lateness" in submittal_headline(undated), submittal_headline(undated)

_rb = open(os.path.join(HERE, "src", "aec_api", "report_builders", "construction.py"),
           encoding="utf-8").read()
assert "dated_count" in _rb and "turnaround_count" in _rb, "the exported KPIs still carry no basis"
assert 'r.kpi("Basis", s["coverage_note"])' in _rb, "the export drops the engine's sentence"
assert "needs_resubmittal" in _rb, "the exported register cannot mark a row as coming back"

print(f"test_submittals OK — terminal_states reproduces rfi.CLOSED_STATES {sorted(rfi.CLOSED_STATES)} "
      f"and corrects submittals to {S.terminal_states(sub_mod)}; a Revise & Resubmit row 6 weeks "
      f"late is {rej['open_count']} open / {rej['overdue_count']} overdue "
      f"(was 0/0); 40 undated submittals report {undated['overdue_count']} overdue over "
      f"{undated['dated_count']} assessable")
