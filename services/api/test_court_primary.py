"""COURT-SPLIT — ball-in-court was computed twice, by two rules, and 10 states disagreed.

`modules_query.court_party` answers "whose move is it". The web register answered the same question
itself, by a different rule: `court_party` took the FIRST outgoing transition, `register.ts` unioned
the parties of ALL of them. Derived over 139 modules and 267 workflow states, **10 states in 9
modules** produced different answers — on an open RFI the screen showed Consultant, OwnersRep *and*
GC, while every report said Consultant/OwnersRep, the GC appearing only because it can `void`.

*An escape hatch is not a move somebody owes.* The server's reading was the better one and is what
the money reports consume, so it survives — but it rested on a premise nothing could check:

    "module authors list the primary forward action first"

**That premise is false in two places**, and they are the ones where it matters most:

    pull_plan_task.made_ready  first = `reconstrain` (back to `pulled`)   owed = `commit`
    permit.applied             first = `issue`                            owed = `start_review`

**And it cannot be rescued by deriving "forward" from the declared state order**, which is the
obvious fix and is measurably wrong: `action_item.states` is `['done', 'open']` — alphabetical, not
a progression. Under that reading 45 states have no forward transition at all and 39 have several.
*A convention nothing can check is a convention that has already drifted.*

So the primary is DECLARED (`"primary": true` on one transition) or the state is declared `resting`
— reachable, but owing nobody anything. This gate derives the states where the declaration actually
matters and requires each to carry one.

**The population is 17, not 267, and that bound is the design.** 199 states have a single outgoing
transition and 51 have several that all carry the same parties: for 250 of them the choice cannot
change the answer, so they need no declaration and none was added. A rule that demanded 267 edits
would have been abandoned halfway and left the tree half-declared.

Three answers become **None** rather than changing party: `decision.decided`,
`information_container.published`, `spec_section.issued` are resting. They previously named a party,
which put closed records into ball-in-court rollups as though someone were sitting on them.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_court_primary.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_courtprimary.db"
os.environ["STORAGE_DIR"] = "./test_courtprimary_storage"

for f in ("./test_courtprimary.db",):
    if os.path.exists(f):
        os.remove(f)

import copy  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import module_schema  # noqa: E402
from aec_api import modules_query as mq  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.modules_registry import REGISTRY  # noqa: E402

FAILED: list[str] = []


def check(label, cond, detail=""):
    (print(f"PASS  {label}   {detail}") if cond
     else (FAILED.append(label), print(f"FAIL  {label}   {detail}")))


def ambiguous(registry) -> list[tuple[str, str]]:
    """Every (module, state) where which outgoing transition you pick CHANGES the answer.

    Derived, not listed: a state qualifies when its outgoing transitions do not all carry the same
    party set. Anything else is unaffected by the choice, so requiring a declaration there would be
    ceremony — and ceremony is what does not get maintained.
    """
    out = []
    for key, mod in sorted(registry.items()):
        ts = ((mod.get("workflow") or {}).get("transitions")) or []
        seen = []
        for t in ts:
            if t["from"] not in seen:
                seen.append(t["from"])
        for s in seen:
            outgoing = [t for t in ts if t["from"] == s]
            if len(outgoing) < 2:
                continue
            if len({tuple(sorted(t.get("party") or [])) for t in outgoing}) > 1:
                out.append((key, s))
    return out


def unresolved(registry) -> list[str]:
    """Ambiguous states declaring neither a primary transition nor `resting`."""
    bad = []
    for key, state in ambiguous(registry):
        wf = registry[key].get("workflow") or {}
        if state in (wf.get("resting") or []):
            continue
        if any(t.get("primary") for t in wf.get("transitions", []) if t["from"] == state):
            continue
        bad.append(f"{key}.{state}")
    return bad


with TestClient(app):
    check("the registry is loaded before anything is derived from it", len(REGISTRY) > 130,
          f"{len(REGISTRY)} modules")

    amb = ambiguous(REGISTRY)
    check("the ambiguous population is derived and non-trivial", 10 <= len(amb) <= 40,
          f"{len(amb)} states where the choice changes the answer, out of 267 with outgoing "
          f"transitions")
    check("every ambiguous state declares a primary or is resting", not unresolved(REGISTRY),
          f"unresolved: {unresolved(REGISTRY)}" if unresolved(REGISTRY) else
          f"all {len(amb)} resolved")

    # ---- the derivation must FIND an unresolved state, or it is only reporting good news ---------
    stripped = copy.deepcopy(dict(REGISTRY))
    victim = amb[0]
    wf = stripped[victim[0]]["workflow"]
    wf["resting"] = [s for s in (wf.get("resting") or []) if s != victim[1]]
    for t in wf["transitions"]:
        if t["from"] == victim[1]:
            t.pop("primary", None)
    check("stripping a declaration is CAUGHT", f"{victim[0]}.{victim[1]}" in unresolved(stripped),
          f"removed {victim[0]}.{victim[1]}'s declaration; unresolved now {unresolved(stripped)}")

    # ...and a state that is NOT ambiguous must never be demanded of.
    same = copy.deepcopy(dict(REGISTRY))
    for m in same.values():
        for t in ((m.get("workflow") or {}).get("transitions")) or []:
            t["party"] = ["GC"]
    check("a tree where every transition shares one party demands nothing",
          ambiguous(same) == [] and unresolved(same) == [],
          "the population is about DISAGREEMENT between transitions, not about their number")

    # ---- the rule itself -------------------------------------------------------------------------
    check("court_party reads the declared primary, not the first transition",
          mq.court_party(REGISTRY["pull_plan_task"], "made_ready") == "GC/Subcontractor",
          f"got {mq.court_party(REGISTRY['pull_plan_task'], 'made_ready')!r} — `reconstrain` is "
          f"listed first and is a rollback; `commit` is the owed move")
    check("...and the correction is real, not a no-op",
          mq.court_party(REGISTRY["permit"], "applied") == "GC",
          f"got {mq.court_party(REGISTRY['permit'], 'applied')!r} — nothing is issued before review")
    check("a resting state owes nobody", mq.court_party(REGISTRY["decision"], "decided") is None,
          f"got {mq.court_party(REGISTRY['decision'], 'decided')!r}")
    check("...and so do the other two",
          mq.court_party(REGISTRY["information_container"], "published") is None
          and mq.court_party(REGISTRY["spec_section"], "issued") is None)
    check("an unambiguous state is unchanged", mq.court_party(REGISTRY["rfi"], "draft") == "GC")
    check("a terminal state is still None", mq.court_party(REGISTRY["rfi"], "closed") is None)
    check("no state at all is None", mq.court_party(REGISTRY["rfi"], None) is None)

    # MUTATION: ignore the declaration and the two corrections must revert. Without this the checks
    # above would pass on a build where `court_party` had gone back to `out[0]` and only the config
    # carried the intent.
    real = mq.court_party
    try:
        def first_only(mod, state):
            if not state:
                return None
            for t in (mod.get("workflow") or {}).get("transitions", []):
                if t["from"] == state:
                    return "/".join(t.get("party") or []) or None
            return None
        mq.court_party = first_only
        check("ignoring the declaration reinstates BOTH wrong answers",
              mq.court_party(REGISTRY["pull_plan_task"], "made_ready") == "GC/PM"
              and mq.court_party(REGISTRY["permit"], "applied") == "GC/OwnersRep",
              "so the assertions above are testing the reader, not just the config")
    finally:
        mq.court_party = real

    # ---- the schema refuses the two shapes that would bring the ambiguity back -------------------
    def probs(wf):
        return module_schema.validate_module({"key": "probe", "name": "Probe",
                                              "fields": [{"name": "a", "type": "text"}],
                                              "workflow": wf})

    _ok = {"initial": "a", "states": ["a", "b", "c"],
           "transitions": [{"from": "a", "to": "b", "action": "go", "party": ["GC"], "primary": True},
                           {"from": "a", "to": "c", "action": "stop", "party": ["Owner"]}]}
    check("a well-formed declaration validates", not probs(_ok), f"{probs(_ok)}")

    _two = copy.deepcopy(_ok)
    _two["transitions"][1]["primary"] = True
    check("two primaries on one state are refused", any("primary" in p for p in probs(_two)),
          f"{probs(_two)}")

    _both = copy.deepcopy(_ok)
    _both["resting"] = ["a"]
    check("primary AND resting on one state is refused", any("resting" in p for p in probs(_both)),
          f"{probs(_both)}")

    _ghost = copy.deepcopy(_ok)
    _ghost["resting"] = ["nope"]
    check("a resting state that is not a state is refused", any("nope" in p for p in probs(_ghost)),
          f"{probs(_ghost)}")

# ---- END TO END: a transition into a resting state must not invent an owner ----------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Court Split"}).json()["id"]
    r = c.post(f"/projects/{pid}/modules/decision",
               json={"data": {"subject": "Slab thickness", "question": "200 or 250?"}})
    check("a decision record exists", r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}")
    #
    # **`check`'s DETAIL is evaluated even when the condition is false** — Python builds both
    # arguments before the call. So a detail that dereferences the very thing under test turns a FAIL
    # into a traceback, and a traceback skips every later check AND the summary line. Reproduced:
    # with `row = None`, `f"got {row.get('x')}"` raises `AttributeError` and the gate reports nothing
    # at all, having found a real defect.
    #
    # *A checker that dies instead of reporting is the same family as one that answers instead of
    # failing* — both end with a run that tells you less than it knows. Every id below is therefore
    # bound defensively, and every detail reads through a guard. Found by review.
    decision_id = r.json().get("id") if r.status_code in (200, 201) else None
    before = r.json().get("party_owner") if r.status_code in (200, 201) else None
    if decision_id:
        d = c.post(f"/projects/{pid}/modules/decision/{decision_id}/transition",
                   json={"action": "decide"})
        if d.status_code == 200:
            after = d.json()
            check("deciding moves the record", after.get("workflow_state") == "decided",
                  f"state={after.get('workflow_state')!r}")
            check("...and leaves the last owner rather than naming a new one",
                  after.get("party_owner") == before,
                  f"before={before!r} after={after.get('party_owner')!r} — a resting state owes "
                  f"nobody, so `transition` must leave party_owner alone exactly as it does for a "
                  f"terminal state")
        else:
            check("deciding moves the record", False, f"{d.status_code} {d.text[:200]}")

    # ---- the routes must actually SEND it, or the register reads a key nobody emits --------------
    #
    # `register.ts` deliberately has no local fallback — recomputing would be the second
    # implementation again — so if a route stops sending this the screen silently shows a dash. Both
    # routes are asserted, because the table and the detail view are served by different ones and it
    # was the detail view that would have been missed.
    rr = c.post(f"/projects/{pid}/modules/rfi",
                json={"data": {"subject": "Who answers?", "question": "this"}})
    check("an RFI exists to read back", rr.status_code in (200, 201),
          f"{rr.status_code} {rr.text[:200]}")
    rid = rr.json().get("id") if rr.status_code in (200, 201) else None
    row = one = None
    if rid:
        c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", json={"action": "submit"})
        listed = c.get(f"/projects/{pid}/modules/rfi").json()
        listed = listed.get("items", listed) if isinstance(listed, dict) else listed
        # `isinstance(listed, list)` AFTER the envelope unwrap: a 4xx/5xx body is a dict with no
        # `items`, so the unwrap hands the ERROR OBJECT back and iterating it yields its string
        # keys — `x.get` then raises and the gate dies instead of reporting the route failure.
        listed = listed if isinstance(listed, list) else []
        row = next((x for x in listed if isinstance(x, dict) and x.get("id") == rid), None)
        one = c.get(f"/projects/{pid}/modules/rfi/{rid}").json()

    check("the LIST route sends ball_in_court", row is not None and "ball_in_court" in row,
          f"keys: {sorted(row)[:12]}..." if row else "the record was not listed")
    check("...and it is the server's answer, not the union",
          bool(row) and row.get("ball_in_court") == "Consultant/OwnersRep",
          f"got {row.get('ball_in_court')!r} — the union would have added GC for `void`"
          if row else "no row to read")
    check("the RECORD route sends ball_in_court", bool(one) and "ball_in_court" in one,
          f"keys: {sorted(one)[:12]}..." if one else "the record was not fetched")
    check("...and both routes agree",
          bool(row) and bool(one) and one.get("ball_in_court") == row.get("ball_in_court"),
          f"list={(row or {}).get('ball_in_court')!r} record={(one or {}).get('ball_in_court')!r}")

    # A resting record must send the key with a null, not omit it: a key that appears only sometimes
    # is indistinguishable from a key the server forgot.
    dd = c.get(f"/projects/{pid}/modules/decision/{decision_id}").json() if decision_id else None
    check("a resting record sends the key as null rather than omitting it",
          bool(dd) and "ball_in_court" in dd and dd["ball_in_court"] is None,
          f"got {dd.get('ball_in_court', '<absent>')!r}" if dd else "no decision record to read")

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_court_primary OK")
raise SystemExit(1 if FAILED else 0)
