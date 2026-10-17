"""DASH-TERMINAL — the GC dashboard's headline KPIs ran on two hardcoded state sets.

`dashboard.build` held `terminal_states = {"closed","answered","verified","done"}` and
`open_states = {open,submitted,draft,issued,scheduled,investigating,applied,agenda,proposed,pending}`
and applied both to all 139 modules. Both were wrong in both directions.

**The derivation was already in the tree THREE times, one of them in the same file as the
dashboard's own data source.** `modules._terminal_states` (feeding `due_feed`),
`workflow_config.validate`'s inline `shipped_dead`, and `submittals.terminal_states` all computed
"a state no transition leaves"; `dashboard.build` computed nothing and hardcoded a literal. There is
one definition now -- `workflow_config.terminal_states` -- and the other three delegate to it.

Four things are asserted here:

**1. The same screen showed two overdue numbers that disagreed.** `due_feed` drives the portal's
overdue QUEUE and resolves terminal states per module, correctly. The `overdue` KPI used the
literal. Measured: three voided RFIs, all past due, nothing else on the project -> **KPI 3, queue
0**. `rfi.RFI_WITHDRAWN` exists to say *"a voided RFI was retracted: it carries no cost or schedule
exposure"*, and the KPI counted all three as late.

**2. The overdue bound is SMALL, and the first draft of this finding got it wrong in the
flattering direction.** Structurally 74 (module, state) pairs are terminal in their module and
absent from the literal -- but the overdue loop only scans modules with a due-date field, which is
**16 of 139**, so 69 of those pairs never reach the KPI. Real exposure: 5 pairs
(`decision.superseded`, `due_diligence.cleared`, `rfi.void`, `risk.accepted`, `selection.approved`)
plus `rfi.answered` in the other direction. *A severity asserted over the wrong population is still
wrong when the defect is real*, so the bound is asserted here rather than described.

**3. The OPEN KPIs are the large half: 140 (module, state) pairs live in their module and in
NEITHER set**, so no KPI counted them -- 76 of 139 modules. Five of the six headline KPIs
undercounted by name.

**4. An answered RFI is open, and three places used to disagree.** The workflow has
`answered -> closed | accept [GC]` AND `answered -> open | reopen [GC]`, `rfi.COURT["answered"]` is
"GC (accept)", and `rfi.CLOSED_STATES` is `("closed","void")` -- so `rfi_register.open_count` always
counted it open while `dashboard._overdue` and the CEP report's "Open RFIs" KPI called it finished.
"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_dash_terminal.db"
os.environ["STORAGE_DIR"] = "./test_storage_dash_terminal"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_dash_terminal.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules as me  # noqa: E402
from aec_api import rfi  # noqa: E402
from aec_api import workflow_config as W  # noqa: E402
from aec_api.main import app  # noqa: E402

me.load_registry()                    # REGISTRY is empty until this runs; the app does it on
#                                     startup, and the sweeps below run before any request.
assert len(me.REGISTRY) > 100, f"only {len(me.REGISTRY)} modules loaded -- the sweeps below " \
    "derive their populations from this registry, and an empty one reports a clean tree"

def declared_live(mod: dict) -> list[str]:
    """The states a module DECLARES as non-terminal.

    Local on purpose. `workflow_config` used to export this as `live_states` and `dashboard.build`
    used it as its open set, which reintroduced this item's own defect -- `state_counts_all` reports
    what the DATA holds, not what the module declares, so a record in an undeclared state fell into
    neither half. The helper is deleted (`test_tested_but_unwired` reported it callerless the moment
    the dashboard stopped using it, and that gate's header says the frozen list is not an allowlist
    to ignore). It lives here because this file's job is to show the derivation is WRONG for the
    dashboard's question, and a wrong derivation does not belong in the shared module where the next
    reader would reach for it.
    """
    term = set(W.terminal_states(mod))
    return [s for s in map(str, (mod.get("workflow") or {}).get("states") or []) if s not in term]


HERE = os.path.dirname(os.path.abspath(__file__))
PAST = "2020-01-01"
#: The literal `dashboard.build` used to hold, replayed below against real data.
OLD_TERMINAL = {"closed", "answered", "verified", "done"}
OLD_OPEN = {"open", "submitted", "draft", "issued", "scheduled", "investigating",
            "applied", "agenda", "proposed", "pending"}


def _mod(key):
    with open(os.path.join(HERE, "modules", key, "module.json"), encoding="utf-8") as fh:
        return json.load(fh)


# --- 0. ONE definition, and the other three delegate to it --------------------------------------
_rfi_mod = _mod("rfi")
assert W.terminal_states(_rfi_mod) == sorted(rfi.CLOSED_STATES), (
    "the shared helper must reproduce rfi.CLOSED_STATES, a tuple hand-written in another module")
assert set(me._terminal_states(_rfi_mod)) == set(W.terminal_states(_rfi_mod)), "modules delegates"
# `live` is the COMPLEMENT, not a second allowlist -- the half that went stale was the allowlist.
assert set(W.terminal_states(_rfi_mod)) | set(declared_live(_rfi_mod)) == set(
    _rfi_mod["workflow"]["states"]), "terminal + live must partition the declared states"
assert not (set(W.terminal_states(_rfi_mod)) & set(declared_live(_rfi_mod))), "disjoint"
# the latent KeyError the old `modules._terminal_states` carried: a transition with no `from`
assert me._terminal_states({"workflow": {"states": ["a", "b"], "transitions": [{"to": "b"}]}}) \
    == {"a", "b"}, "a transition without a `from` must be skipped, not raise"
# `answered` is NOT terminal -- it has TWO ways out, which is why calling it done was wrong
_out = [t for t in _rfi_mod["workflow"]["transitions"] if t.get("from") == "answered"]
assert {t["action"] for t in _out} == {"accept", "reopen"}, _out
assert "answered" in declared_live(_rfi_mod) and "answered" in OLD_TERMINAL, "the disagreement"

# --- 1. the bound: how much of the structural count can actually reach the overdue KPI ----------
due_mods = [k for k, m in me.REGISTRY.items() if me._due_field_name(m)]
assert 10 <= len(due_mods) <= 40, (
    f"{len(due_mods)} modules carry a due field -- the overdue loop's whole population. If this "
    "moved a lot, re-measure the exposure below rather than trusting these numbers.")
inflating, hiding = {}, {}
for k in due_mods:
    term = set(W.terminal_states(me.REGISTRY[k]))
    live = set(declared_live(me.REGISTRY[k]))
    if term - OLD_TERMINAL:
        inflating[k] = sorted(term - OLD_TERMINAL)
    if live & OLD_TERMINAL:
        hiding[k] = sorted(live & OLD_TERMINAL)
# the finished states the old KPI counted as late, and the live one it called finished
assert inflating == {"decision": ["superseded"], "due_diligence": ["cleared"], "rfi": ["void"],
                     "risk": ["accepted"], "selection": ["approved"]}, inflating
assert hiding == {"rfi": ["answered"]}, hiding
# ...and the structural count is much larger, which is the number NOT to quote as the severity
structural = sum(len(set(W.terminal_states(m)) - OLD_TERMINAL) for m in me.REGISTRY.values())
assert structural > 10 * sum(len(v) for v in inflating.values()), (
    f"structural={structural} vs reachable={sum(len(v) for v in inflating.values())} -- the point "
    "of this assertion is that they are far apart")

# --- 2. the open KPIs are the large half --------------------------------------------------------
invisible = {k: sorted(set(declared_live(m)) - OLD_OPEN - OLD_TERMINAL)
             for k, m in me.REGISTRY.items()}
invisible = {k: v for k, v in invisible.items() if v}
assert len(invisible) > 60, f"only {len(invisible)} modules had a live state no KPI counted"
for k, expect in (("cor", ["approved"]), ("punchlist", ["ready"]), ("ncr", ["dispositioned"]),
                  ("deficiency", ["corrected"]), ("issue", ["resolved"]),
                  ("coordination_issue", ["assigned", "resolved"]),
                  ("observation", ["assigned", "corrected"])):
    assert invisible.get(k) == expect, (k, invisible.get(k), expect)


def mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code in (200, 201), (key, r.status_code, r.text[:200])
    return r.json()["id"]


def tr(c, pid, key, rid, action):
    r = c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})
    assert r.status_code == 200, (key, action, r.status_code, r.text[:200])


def _replay_old_overdue(pid):
    """The pre-fix `overdue` computation, against the same data. Both halves of it: the literal was
    the SQL exclusion handed to `active_records` AND the test inside `_overdue`."""
    from aec_api.db import SessionLocal
    from aec_api.timeutil import utc_today
    today = utc_today().isoformat()
    db = SessionLocal()
    n = 0
    try:
        for key, mod in me.REGISTRY.items():
            if not me._due_field_name(mod) or key not in me.TABLES:
                continue
            for r in me.active_records(db, key, pid, OLD_TERMINAL):
                due = r["data"].get("due_date")
                if due and str(due)[:10] < today and r["workflow_state"] not in OLD_TERMINAL:
                    n += 1
    finally:
        db.close()
    return n


with TestClient(app) as c:
    # --- 3. THE DEFECT: two numbers on one screen, disagreeing ----------------------------------
    pid = c.post("/projects", json={"name": "Voided"}).json()["id"]
    for i in range(3):
        v = mk(c, pid, "rfi", {"subject": f"Moot {i}", "question": "?", "due_date": PAST})
        tr(c, pid, "rfi", v, "submit")
        tr(c, pid, "rfi", v, "void")
    dash = c.get(f"/projects/{pid}/dashboard").json()
    queue = c.get(f"/projects/{pid}/due-feed").json()["counts"]["overdue"]
    assert _replay_old_overdue(pid) == 3, "the pre-fix KPI counted three retracted RFIs as late"
    assert queue == 0, "the queue on the same screen always said zero"
    assert dash["kpis"]["overdue"] == 0, dash["kpis"]
    assert dash["kpis"]["overdue"] == queue, "the KPI and the queue must now agree"

    # --- 4. the live states no KPI counted, and the overdue state it missed ----------------------
    pid2 = c.post("/projects", json={"name": "Live"}).json()["id"]
    a = mk(c, pid2, "rfi", {"subject": "Beam", "question": "?", "due_date": PAST,
                            "answer": "W18x40"})
    tr(c, pid2, "rfi", a, "submit")
    tr(c, pid2, "rfi", a, "respond")                      # -> answered: GC must accept or reopen
    pl = mk(c, pid2, "punchlist", {"description": "Paint", "due_date": PAST})
    tr(c, pid2, "punchlist", pl, "ready_to_inspect")      # -> ready
    n = mk(c, pid2, "ncr", {"subject": "Honeycomb", "severity": "Major", "disposition": "Repair",
                            "due_date": PAST})
    tr(c, pid2, "ncr", n, "disposition")                  # -> dispositioned
    d = mk(c, pid2, "deficiency", {"description": "Scratch", "severity": "Minor",
                                   "due_date": PAST})
    tr(c, pid2, "deficiency", d, "correct")               # -> corrected
    co = mk(c, pid2, "cor", {"subject": "Steel", "amount": 25000})
    tr(c, pid2, "cor", co, "submit")
    tr(c, pid2, "cor", co, "approve")                     # -> approved: live money
    k2 = c.get(f"/projects/{pid2}/dashboard").json()["kpis"]
    q2 = c.get(f"/projects/{pid2}/due-feed").json()
    # every one of these was 0 before: the state is live and was in neither hardcoded set
    assert k2["open_rfis"] == 1, k2            # answered
    assert k2["pending_change_orders"] == 1, k2  # approved
    assert k2["open_punchlist"] == 1, k2       # ready
    assert k2["open_quality"] == 2, k2         # dispositioned NCR + corrected deficiency
    # the answered RFI is late, and the old KPI could not see it because it called `answered` done
    assert ("rfi", "answered") in {(x["module"], x["state"]) for x in q2["overdue"]}, q2["overdue"]
    assert k2["overdue"] == q2["counts"]["overdue"] == 4, (k2["overdue"], q2["counts"])

    # --- 5. kpi_basis states what each KPI counted, per module, from the workflow in force ------
    dash2 = c.get(f"/projects/{pid2}/dashboard").json()
    basis = dash2["kpi_basis"]
    # **The two halves are asymmetric ON PURPOSE, and the asymmetry is a bug this item shipped
    # before `test_trunc_counted` caught it.** `terminal` is DECLARED -- "no transition leaves this
    # state" is the one thing a workflow can answer. `open` is OBSERVED: the states this project's
    # data actually holds, minus the terminal ones. Deriving open from the DECLARED live states
    # instead made a record sitting in an undeclared state (written before a workflow change, or
    # imported) fall into neither half, so it vanished from every open KPI -- this item's own
    # defect, one layer along.
    assert basis["rfi"] == {"open": ["answered"], "terminal": ["closed", "void"]}, basis["rfi"]
    assert basis["cor"] == {"open": ["approved"], "terminal": ["executed", "rejected"]}, basis["cor"]
    # the same population as `by_module`: only modules that contributed a record
    assert set(basis) == {m["key"] for m in dash2["by_module"]}, "basis and by_module must agree"
    for key, b in basis.items():
        assert b["terminal"] == sorted(W.terminal_states(me.REGISTRY[key])), key
        # every state reported open is observed, non-terminal, and a subset of what is declared
        by_state = next(m["by_state"] for m in dash2["by_module"] if m["key"] == key)
        assert b["open"] == sorted(s for s in by_state if s not in b["terminal"]), key
        assert not (set(b["open"]) & set(b["terminal"])), key
    # AND THE HOLE IS CLOSED: an UNDECLARED state counts as open rather than disappearing.
    _undeclared = {"limbo"}
    _fake = {"workflow": {"states": ["a", "b"], "transitions": [{"from": "a", "to": "b"}]}}
    assert W.terminal_states(_fake) == ["b"], W.terminal_states(_fake)
    assert _undeclared - set(declared_live(_fake)) == _undeclared, (
        "`limbo` is not declared, so a declared-live derivation cannot see it -- which is why the "
        "dashboard takes the complement over the OBSERVED states instead")

    # --- 6. an OVERRIDDEN workflow changes the answer, THROUGH THE DASHBOARD --------------------
    # WORKFLOW-DARK. Terminal-ness is a property of the EDGES, so an override that removes the way
    # out of a state makes it terminal without any state NAME changing -- which is the whole reason
    # a hardcoded set of names cannot be right.
    #
    # **Asserted through the route, not on the helper.** The first draft of this block called
    # `W.effective` directly and checked its output; the mutation replacing
    # `workflow_config.effective(mod, pid, wf_cfg)` with a bare `mod` in `dashboard.build` then
    # PASSED, because nothing tied the dashboard to the override. That is the same slip this
    # session made on `projecthealth.submittal_status` hours earlier: *asserting a helper is not
    # asserting its caller.*
    OVERRIDE = [
        {"from": "draft", "to": "open", "action": "submit"},
        {"from": "open", "to": "answered", "action": "respond", "requires": ["answer"]},
        {"from": "open", "to": "void", "action": "void"},
        # ...and NO way out of `answered`: this job treats a received answer as the end of it.
    ]
    # Saving it on `pid2` is REFUSED, and that refusal is the stranding guard doing its job: a
    # record is sitting in `answered` and the override would leave it no way out. Pinned here
    # because it is the behaviour `validate`'s carve-out is carved out OF.
    refused = c.put(f"/projects/{pid2}/workflow/rfi", json={"transitions": OVERRIDE})
    assert refused.status_code == 422, (refused.status_code, refused.text[:200])
    assert "strand live records" in refused.text and "'answered'" in refused.text, refused.text[:300]

    # So: a FRESH project, the override saved before any record exists.
    pid3 = c.post("/projects", json={"name": "Overridden"}).json()["id"]
    rr = c.put(f"/projects/{pid3}/workflow/rfi", json={"transitions": OVERRIDE})
    assert rr.status_code == 200, rr.text[:300]
    a3 = mk(c, pid3, "rfi", {"subject": "Beam", "question": "?", "due_date": PAST,
                             "answer": "W18x40"})
    tr(c, pid3, "rfi", a3, "submit")
    tr(c, pid3, "rfi", a3, "respond")
    over_dash = c.get(f"/projects/{pid3}/dashboard").json()
    assert over_dash["kpi_basis"]["rfi"] == {
        # nothing OBSERVED is open: the project's one RFI sits in `answered`...
        "open": [],
        # ...which this project's workflow makes terminal, where the shipped one does not.
        "terminal": ["answered", "closed", "void"]}, over_dash["kpi_basis"]["rfi"]
    assert "answered" not in W.terminal_states(me.REGISTRY["rfi"]), "shipped: still live"
    # **THE SAME RECORD IN THE SAME STATE**, past due, is live on pid2 and finished on pid3 --
    # purely because of the transitions in force. No set of state NAMES can express that.
    assert over_dash["kpis"]["open_rfis"] == 0, over_dash["kpis"]
    assert over_dash["kpis"]["overdue"] == 0, over_dash["kpis"]
    assert k2["open_rfis"] == 1, "the same shape on the un-overridden project is still open"
    # ...and the shipped module is untouched, which is why this must be resolved per project
    assert "answered" in declared_live(me.REGISTRY["rfi"]), "the shipped module is unchanged"

    # --- 6b. `validate`'s carve-out for a genuinely terminal state -------------------------------
    # `validate` refuses an override that strands live records, with a carve-out: a state that was
    # ALREADY terminal in the shipped workflow should have no exit, so having none is not stranding.
    # That carve-out routes through `terminal_states` now, and it was UNASSERTED before this item --
    # `shipped_dead = set()` passed `test_workflow_config.py`, so a mutation making `validate`
    # refuse legitimate overrides went unnoticed. The override just saved is exactly that case:
    # `closed` and `void` are shipped-terminal and the override gives them no exit.
    assert rr.json()["saved"] == 3, rr.json()
    # The carve-out is about states terminal in the SHIPPED workflow. `closed` is one: it has no
    # exit there, so an override that also gives it none is not stranding anybody. A project with a
    # record sitting in `closed` is the fixture that tells the carve-out apart from its absence.
    pid4 = c.post("/projects", json={"name": "Closed"}).json()["id"]
    done = mk(c, pid4, "rfi", {"subject": "Answered and accepted", "question": "?",
                               "answer": "yes"})
    tr(c, pid4, "rfi", done, "submit")
    tr(c, pid4, "rfi", done, "respond")
    tr(c, pid4, "rfi", done, "accept")                 # -> closed, a shipped-terminal state
    assert c.get(f"/projects/{pid4}/modules/rfi/{done}").json()["workflow_state"] == "closed"
    # No exit from `closed` in this override, and a record is sitting there. Must be ACCEPTED.
    ok = c.put(f"/projects/{pid4}/workflow/rfi", json={"transitions": [
        {"from": "draft", "to": "open", "action": "submit"},
        {"from": "open", "to": "answered", "action": "respond", "requires": ["answer"]},
        {"from": "answered", "to": "closed", "action": "accept"},
    ]})
    assert ok.status_code == 200, (
        "the carve-out for a shipped-terminal state is gone: `validate` now refuses an override "
        f"that strands nobody -- {ok.text[:220]}")
    assert "closed" in W.terminal_states(me.REGISTRY["rfi"]), "`closed` is shipped-terminal"

    # --- 7. the third disagreeing site: the exported "Open RFIs" KPI ----------------------------
    reg = c.get(f"/projects/{pid2}/rfi/register").json()
    assert reg["open_count"] == 1, reg              # the answered RFI
    _cep_src = open(os.path.join(HERE, "src", "aec_api", "report_builders", "construction.py"),
                    encoding="utf-8").read()
    # Comments stripped first: the fix's OWN comment quotes the literal it replaced, so an
    # unstripped scan reads the documentation as the defect -- which is what the first draft of
    # this assertion did.
    _cep = "\n".join(ln for ln in _cep_src.splitlines() if not ln.strip().startswith("#"))
    assert len(_cep) < len(_cep_src), "the comment stripper removed nothing"
    assert 'not in rfi_engine.CLOSED_STATES' in _cep, (
        "the CEP report's Open RFIs KPI still hardcodes its own closed set")
    assert 'not in ("closed", "answered", "void")' not in _cep, "the old literal is still live code"

print(f"test_dash_terminal OK — 3 voided RFIs past due: pre-fix KPI 3, queue 0, now {0}=={0}; "
      f"{len(inflating)} due-carrying modules could inflate overdue (not the {structural} "
      f"structural pairs); {len(invisible)} of {len(me.REGISTRY)} modules had a live state no "
      f"open KPI counted")
