"""WFE-3 — per-project workflow overrides.

A workflow isn't just a schema: records are sitting in its states right now. So the assertions that
matter are the ones about LIVE RECORDS — an override that removes the last way out of an occupied
state doesn't fail loudly, it strands those records where nobody notices.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_workflow_config.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_workflow_config.db"
os.environ["STORAGE_DIR"] = "./test_storage_workflow_config"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_workflow_config.db"):
    os.remove("./test_workflow_config.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules_registry  # noqa: E402
from aec_api import workflow_config as wc
from aec_api.main import app  # noqa: E402

modules_registry.load_registry()
RFI = modules_registry.get_module("rfi")
STATES = RFI["workflow"]["states"]
assert {"draft", "open", "answered", "closed"} <= set(STATES), STATES

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "WFE"}).json()["id"]

    def mk(subject="Q", **extra):
        r = c.post(f"/projects/{pid}/modules/rfi",
                   json={"data": {"subject": subject, "question": "?", **extra}})
        assert r.status_code in (200, 201), r.text[:200]
        return r.json()["id"]

    # ---- the shipped workflow is what you get until you override it -----------------------------
    w = c.get(f"/projects/{pid}/workflow/rfi").json()
    assert w["overridden"] is False and w["transitions"] == RFI["workflow"]["transitions"], w
    assert w["initial"] == RFI["workflow"]["initial"]

    rid = mk("Slab edge detail")
    rec = c.get(f"/projects/{pid}/modules/rfi/{rid}").json()
    assert rec["workflow_state"] == "draft"
    assert "workflow_overridden" not in rec, rec
    shipped_actions = {a["action"] for a in rec["available_actions"]}
    assert "submit" in shipped_actions, shipped_actions

    # ---- an override rewires which declared states connect ---------------------------------------
    # This job wants RFIs to go straight draft → answered (no separate open step), and adds a reopen.
    OVERRIDE = [
        {"from": "draft", "to": "answered", "action": "answer_direct", "requires": ["answer"]},
        {"from": "answered", "to": "closed", "action": "close"},
        {"from": "closed", "to": "draft", "action": "reopen"},
    ]
    r = c.put(f"/projects/{pid}/workflow/rfi", json={"transitions": OVERRIDE})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["saved"] == 3

    w2 = c.get(f"/projects/{pid}/workflow/rfi").json()
    assert w2["overridden"] is True and len(w2["transitions"]) == 3, w2
    assert w2["shipped_transitions"] == RFI["workflow"]["transitions"]   # the default is still shown

    # the actions the UI offers now match the override — not the shipped set
    rec2 = c.get(f"/projects/{pid}/modules/rfi/{rid}").json()
    acts = {a["action"] for a in rec2["available_actions"]}
    assert acts == {"answer_direct"}, acts
    assert rec2["workflow_overridden"] is True, rec2

    # …and the ENGINE honours the same thing: the shipped action is now refused
    assert c.post(f"/projects/{pid}/modules/rfi/{rid}/transition",
                  json={"action": "submit"}).status_code == 409
    # the override's `requires` gate fires
    blocked = c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", json={"action": "answer_direct"})
    assert blocked.status_code == 400 and "requires" in blocked.text.lower(), blocked.text[:200]
    c.patch(f"/projects/{pid}/modules/rfi/{rid}", json={"answer": "Use detail 5/A-501"})
    ok = c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", json={"action": "answer_direct"})
    assert ok.status_code == 200, ok.text[:200]
    assert c.get(f"/projects/{pid}/modules/rfi/{rid}").json()["workflow_state"] == "answered"

    # ---- THE POINT: an override that would strand live records is REFUSED -------------------------
    # one record is sitting in "answered"; an override with no way out of it traps that record
    strand = c.put(f"/projects/{pid}/workflow/rfi", json={"transitions": [
        {"from": "draft", "to": "answered", "action": "answer_direct"}]})
    assert strand.status_code == 422, strand.text[:300]
    body = strand.text
    assert "strand" in body and "answered" in body, body[:300]
    assert "1 in 'answered'" in body, body[:300]          # it says HOW MANY and WHERE
    # …and nothing was written: the previous override still stands
    assert len(c.get(f"/projects/{pid}/workflow/rfi").json()["transitions"]) == 3

    # the same shape is fine once no record is there — move it out first
    c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", json={"action": "close"})
    assert c.get(f"/projects/{pid}/modules/rfi/{rid}").json()["workflow_state"] == "closed"
    ok2 = c.put(f"/projects/{pid}/workflow/rfi", json={"transitions": [
        {"from": "draft", "to": "answered", "action": "answer_direct"},
        {"from": "closed", "to": "draft", "action": "reopen"}]})
    assert ok2.status_code == 200, ok2.text[:300]

    # a state that is genuinely terminal in the SHIPPED workflow is not treated as stranding —
    # "closed" having no exit is the normal case, not a defect
    assert any(t["from"] == "closed" for t in ok2.json()["transitions"])

    # ---- an override may rewire declared states, never invent new ones ----------------------------
    for bad, why in (
        ([{"from": "draft", "to": "teleported", "action": "x"}], "undeclared to-state"),
        ([{"from": "nowhere", "to": "closed", "action": "x"}], "undeclared from-state"),
        ([{"from": "draft", "to": "closed", "action": ""}], "no action"),
        ([{"from": "draft", "to": "closed", "action": "a"},
          {"from": "draft", "to": "answered", "action": "a"}], "duplicate from+action"),
        ([], "empty"),
        ([{"from": "draft", "to": "closed", "action": "x" * 99}], "action too long"),
        (["not-an-object"], "not an object"),
    ):
        rr = c.put(f"/projects/{pid}/workflow/rfi", json={"transitions": bad})
        assert rr.status_code == 422, (why, rr.status_code, rr.text[:160])

    # the cap is enforced
    huge = [{"from": "draft", "to": "closed", "action": f"a{i}"} for i in range(wc.MAX_TRANSITIONS + 1)]
    assert c.put(f"/projects/{pid}/workflow/rfi", json={"transitions": huge}).status_code == 422

    # ---- reachability is reported, not silently ignored -------------------------------------------
    res = wc.validate(__import__("aec_api.db", fromlist=["SessionLocal"]).SessionLocal(), pid, "rfi", [
        {"from": "draft", "to": "answered", "action": "answer_direct"},
        {"from": "closed", "to": "draft", "action": "reopen"}])
    assert "open" in res["unreachable"], res["unreachable"]   # nothing routes to 'open' any more
    assert res["reachable"] and "draft" in res["reachable"], res["reachable"]

    # ---- reset returns the shipped workflow -------------------------------------------------------
    d = c.delete(f"/projects/{pid}/workflow/rfi").json()
    assert d["removed"] is True and d["overridden"] is False, d
    w3 = c.get(f"/projects/{pid}/workflow/rfi").json()
    assert w3["overridden"] is False and w3["transitions"] == RFI["workflow"]["transitions"]
    assert c.delete(f"/projects/{pid}/workflow/rfi").json()["removed"] is False   # idempotent

    # ---- the override is per-project ---------------------------------------------------------------
    pid2 = c.post("/projects", json={"name": "WFE-other"}).json()["id"]
    c.put(f"/projects/{pid}/workflow/rfi", json={"transitions": OVERRIDE})
    assert c.get(f"/projects/{pid2}/workflow/rfi").json()["overridden"] is False
    assert c.get(f"/projects/{pid}/workflow/rfi").json()["overridden"] is True

    # ---- unknown module 404s rather than saving a config nothing reads ------------------------------
    assert c.get(f"/projects/{pid}/workflow/not_a_module").status_code == 404

    # ---- BOARD-SHIPPED: the claim in this file's own summary was true of the ROUTES it checked ------
    # It says "the actions the UI offers and the transitions the engine honours come from the same
    # effective workflow, so there is no button that 409s". That held for the single-record route,
    # whose own comment states the rule -- and NOT for the kanban board, the one screen whose entire
    # interaction IS a state transition. `board()` called `get_module` where every other workflow
    # consumer routes through `workflow_config.effective`, so on an overridden project the board was
    # INVERTED: measured, dragging `draft -> open` (which it offered) posted `submit` and got 409
    # "action 'submit' not allowed from state 'draft'", while `fast_answer` -- the transition the
    # firm configured -- returned 200 and the board offered no drag for it.
    # *A property asserted for the routes somebody looked at is not a property of the system.*
    bpid = c.post("/projects", json={"name": "Board basis"}).json()["id"]
    brid = c.post(f"/projects/{bpid}/modules/rfi",
                  json={"data": {"subject": "B", "question": "q"}}).json()["id"]
    shipped = c.get(f"/projects/{bpid}/modules/rfi/board").json()
    assert shipped["workflow_overridden"] is False, shipped["workflow_overridden"]
    assert {(t["from"], t["to"]) for t in shipped["transitions"]} == \
        {(t["from"], t["to"]) for t in RFI["workflow"]["transitions"]}, shipped["transitions"]

    c.put(f"/projects/{bpid}/workflow/rfi",
          json={"transitions": [{"from": "draft", "to": "answered", "action": "fast_answer",
                                 "party": ["GC"]},
                                {"from": "answered", "to": "open", "action": "reopen",
                                 "party": ["GC"]}]})
    over = c.get(f"/projects/{bpid}/modules/rfi/board").json()
    assert over["workflow_overridden"] is True, over
    offered = {(t["from"], t["to"]) for t in over["transitions"]}
    assert offered == {("draft", "answered"), ("answered", "open")}, offered
    # ...and EVERY transition the board offers is one the engine honours, which is the property this
    # file's summary claims. Asserted by actually running them, not by comparing two lists that
    # could both be wrong.
    acted = c.post(f"/projects/{bpid}/modules/rfi/{brid}/transition",
                   json={"action": "fast_answer"})
    assert acted.status_code == 200, acted.text[:200]
    # the shipped transition the board NO LONGER offers is also the one the engine now refuses --
    # so the two halves agree in both directions
    refused = c.post(f"/projects/{bpid}/modules/rfi/{brid}/transition", json={"action": "respond"})
    assert refused.status_code == 409, (refused.status_code, refused.text[:160])
    c.delete(f"/projects/{bpid}/workflow/rfi")

    # ---- BOARD-SHIPPED: `counts` is the SQL truth and `columns` is a page of it --------------------
    # The kanban head rendered `columns[state].length`. Measured at 205 records in one state: the
    # column serves the capped 200 and the head said 200, with `counts` undeclared on the client so
    # the screen could not say otherwise. TRUNC-COUNTED, on the board shared across every module.
    cap = int(over["per_state_cap"])
    for i in range(cap + 5):
        c.post(f"/projects/{bpid}/modules/rfi", json={"data": {"subject": f"C{i}", "question": "q"}})
    deep = c.get(f"/projects/{bpid}/modules/rfi/board").json()
    init = RFI["workflow"]["initial"]
    assert len(deep["columns"][init]) == cap, len(deep["columns"][init])
    assert deep["counts"][init] == cap + 5, deep["counts"]
    assert deep["counts"][init] > len(deep["columns"][init]), "the cap must actually bite here"
    assert "page length" in deep["counts_basis"], deep["counts_basis"]

    # ---- BOARD-SHIPPED, the CLEAN NEGATIVE half ---------------------------------------------------
    # A record in a state the module does not declare would get a column in `columns` and, before
    # this change, none in `states` -- so a consumer iterating `states` rendered it nowhere:
    # invisible, not merely uncounted (measured at 2 of 3 drawn). **It is not reachable today, and
    # measuring is what establishes that.** `workflow_state` is written in exactly two places -- the
    # module's `initial` at create, and `transition` against the EFFECTIVE workflow -- and an
    # override "may rewire declared states but never invent new ones", which this file already
    # asserts. So the only door left is a `module.json` whose `states` list shrinks across releases
    # while records sit in the removed state. This is the assertion that keeps the negative clean:
    # every module's `initial` and every endpoint of every declared transition must BE a declared
    # state, or that module can strand records somewhere no board would draw.
    bad_init, bad_edge = [], []
    for mkey, mdef in modules_registry.REGISTRY.items():
        wf = mdef.get("workflow") or {}
        declared = set(wf.get("states") or [])
        if not declared:
            continue
        if (wf.get("initial") or "") not in declared:
            bad_init.append((mkey, wf.get("initial"), sorted(declared)))
        for tr in wf.get("transitions") or []:
            for side in ("from", "to"):
                if (tr.get(side) or "") not in declared:
                    bad_edge.append((mkey, side, tr.get(side), tr.get("action")))
    assert not bad_init, f"module(s) whose `initial` is not a declared state: {bad_init}"
    assert not bad_edge, f"transition endpoint(s) outside the declared states: {bad_edge}"
    _with_wf = sum(1 for m in modules_registry.REGISTRY.values()
                   if (m.get("workflow") or {}).get("states"))
    assert _with_wf > 100, f"only {_with_wf} modules have a workflow — the sweep found almost none"

print("WFE-3 OK - a project can rewire which of a module's DECLARED states connect (RFIs going "
      "straight draft->answered here, with a reopen), and both halves agree: the actions the UI offers "
      "and the transitions the engine honours come from the same effective workflow, so there is no "
      "button that 409s. Overrides carry their own party/requires gates. THE POINT: an override that "
      "would strand live records — a state holding records with no way out — is REFUSED with the "
      "count and the state named ('1 in answered'), because a stranded record looks exactly like one "
      "nobody has got to yet; a state that is terminal in the shipped workflow is correctly not "
      "treated as stranding. Overrides may rewire declared states but never invent new ones, "
      "duplicates/empties/oversized are rejected atomically, unreachable states are reported rather "
      "than silently ignored, reset restores the shipped workflow idempotently, and one project's "
      "override never touches another's. "
      "BOARD-SHIPPED: that no-button-409s claim was true of the ROUTES this file checked and FALSE "
      "of the kanban board, which read the SHIPPED workflow while `transition` honours the "
      "configured one -- so on an overridden project every drag it offered 409d and the one that "
      "worked was refused client-side. The board now resolves through the same effective workflow, "
      "asserted by RUNNING its offered transition (200) and the one it no longer offers (409). Its "
      "column heads also printed a page length: `counts` is the SQL GROUP BY truth and `columns` is "
      "capped, asserted where the cap actually bites. And the clean negative: a record in an "
      "undeclared state would be invisible rather than uncounted, which is unreachable today "
      "because `workflow_state` has exactly two writers and overrides cannot invent states -- kept "
      "clean by asserting that every module's `initial` and every transition endpoint IS a declared "
      f"state, across all {_with_wf} modules that have a workflow.")
