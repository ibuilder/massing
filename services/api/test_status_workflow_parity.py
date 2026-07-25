"""A `status` field that offers a value the workflow cannot reach is a module contradicting itself.

`owner_invoice` offered Draft / Submitted / **Approved** / Paid on its status select, while its
workflow had only draft / submitted / paid. Anyone who set the field to Approved got a record whose
two representations of the same fact disagreed — and because every count, filter, board column and
report keys on `workflow_state`, that record silently reported as merely *submitted*. It is the
two-tables-one-format failure: the drift is invisible until something downstream is quietly wrong.

**The rule has to be narrow, or it is worse than nothing.** Most status-ish selects are a *different*
vocabulary from the workflow and rightly so: `company.dbe_status` is a certification (DBE/MBE/WBE),
`project_phase.iso_status` is an ISO 19650 suitability code (S0/S1/S2/A), `change_event.scope_status`
is a determination. Forcing those to equal a workflow would merge unrelated concepts and be a
mechanical check encoding a false premise. So the invariant applies only where the two are provably
the same vocabulary — a field literally named `status` whose options mostly ARE workflow states.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_status_workflow_parity.py
"""
import json
import os
import pathlib
import re

os.environ["DATABASE_URL"] = "sqlite:///./test_status_workflow_parity.db"
os.environ["STORAGE_DIR"] = "./test_storage_status_parity"
if os.path.exists("./test_status_workflow_parity.db"):
    os.remove("./test_status_workflow_parity.db")

MODULES = pathlib.Path(__file__).resolve().parent / "modules"
SAME_VOCAB = 0.5          # ≥ half the options are workflow states → the two mean the same thing


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def audit():
    """Every (module, field) whose status select names a state the workflow cannot reach."""
    drift, checked, skipped = [], 0, []
    for mj in sorted(MODULES.glob("*/module.json")):
        d = json.loads(mj.read_text(encoding="utf-8"))
        wf = d.get("workflow") or {}
        states = {slug(s) for s in (wf.get("states") or [])}
        if not states:
            continue
        for f in d.get("fields") or []:
            if f.get("type") != "select" or not re.fullmatch(r"status", str(f.get("name") or ""), re.I):
                continue
            opts = {o for o in (slug(o) for o in (f.get("options") or [])) if o}
            if not opts:
                continue
            overlap = len(opts & states) / len(opts)
            if overlap < SAME_VOCAB:
                skipped.append((d["key"], round(overlap, 2)))   # a genuinely different vocabulary
                continue
            checked += 1
            unreachable = sorted(opts - states)
            if unreachable:
                drift.append((d["key"], unreachable, sorted(states)))
    return drift, checked, skipped


drift, checked, skipped = audit()
assert checked >= 5, f"the audit found only {checked} same-vocabulary status fields — did it stop working?"
assert not drift, ("status options naming a state the workflow cannot reach:\n" +
                   "\n".join(f"  {k}: {u} not in {s}" for k, u, s in drift))

# ---- the five that were wrong, now pinned so they cannot regress -------------------------------
EXPECTED = {
    "owner_invoice": {"draft", "submitted", "approved", "rejected", "paid"},
    "permit": {"applied", "under_review", "issued", "expired", "closed"},
    "prequalification": {"invited", "submitted", "approved", "rejected"},
    "value_engineering": {"proposed", "under_review", "accepted", "rejected"},
    "document": {"draft", "issued", "superseded", "void"},
}
for key, want in EXPECTED.items():
    d = json.loads((MODULES / key / "module.json").read_text(encoding="utf-8"))
    states = {slug(s) for s in d["workflow"]["states"]}
    assert want <= states, f"{key}: missing {sorted(want - states)}"

# ---- a new state is worthless if nothing can reach it -------------------------------------------
for key in EXPECTED:
    d = json.loads((MODULES / key / "module.json").read_text(encoding="utf-8"))
    wf = d["workflow"]
    states = {slug(s) for s in wf["states"]}
    initial = slug(wf.get("initial") or "")
    reachable = {initial} if initial else set()
    edges = [(slug(t["from"]), slug(t["to"])) for t in wf["transitions"]]
    changed = True
    while changed:                     # transitive closure from the initial state
        changed = False
        for a, b in edges:
            if a in reachable and b not in reachable:
                reachable.add(b)
                changed = True
    assert states <= reachable, f"{key}: {sorted(states - reachable)} unreachable from {initial!r}"
    # and every transition names states the workflow actually declares
    for a, b in edges:
        assert a in states and b in states, f"{key}: transition {a}->{b} names an undeclared state"

# ---- the AIA G702 certification step specifically -------------------------------------------------
oi = json.loads((MODULES / "owner_invoice" / "module.json").read_text(encoding="utf-8"))
tr = {(slug(t["from"]), slug(t["to"])) for t in oi["workflow"]["transitions"]}
assert ("submitted", "approved") in tr, "an owner certifies a pay application before paying it"
assert ("approved", "paid") in tr
# the pre-existing direct path SURVIVES — removing it would strand every in-flight submitted record
assert ("submitted", "paid") in tr, "removing the direct path would strand records mid-flight"
assert ("rejected", "draft") in tr, "a rejected pay app has to be reviseable"
opts = {slug(o) for f in oi["fields"] if f["name"] == "status" for o in f["options"]}
assert opts == {slug(s) for s in oi["workflow"]["states"]}, (opts, oi["workflow"]["states"])

# ---- the narrowness of the rule is itself the point ----------------------------------------------
# Modules whose status vocabulary is genuinely different are SKIPPED, not forced to match. If this
# stopped being true the check would start demanding that a DBE certification become a workflow.
assert skipped, "some status selects are legitimately a different vocabulary; none were skipped"

print(f"STATUS-PARITY OK - {checked} status fields share their module's workflow vocabulary and every "
      f"option is now a reachable state; {len(skipped)} others were correctly left alone. Five modules "
      "were contradicting themselves: owner_invoice offered 'Approved' with no approved state, so a "
      "user setting it produced a record whose two representations of the same fact disagreed — and "
      "since every count, filter and board column keys on workflow_state, that record silently "
      "reported as merely submitted. owner_invoice gained the AIA G702 certification step (an owner "
      "certifies a pay application before paying it) plus a rejection path, permit gained "
      "under_review and expired — the state that carries schedule risk and the one that is a "
      "compliance failure — prequalification gained invited so the pipeline has a beginning, "
      "value_engineering gained under_review, and document gained superseded, which is a different "
      "end from void: superseded was replaced, void was withdrawn. The pre-existing direct "
      "submitted->paid path is kept deliberately, because removing it would strand every in-flight "
      "record. Above all the rule is NARROW: it fires only where the select and the workflow are "
      "provably the same vocabulary, because company.dbe_status is a certification and "
      "project_phase.iso_status is an ISO 19650 suitability code, and demanding those equal a "
      "workflow would be a rigorous-looking check built on a false premise.")
