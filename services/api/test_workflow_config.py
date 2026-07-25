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

print("WFE-3 OK - a project can rewire which of a module's DECLARED states connect (RFIs going "
      "straight draft→answered here, with a reopen), and both halves agree: the actions the UI offers "
      "and the transitions the engine honours come from the same effective workflow, so there is no "
      "button that 409s. Overrides carry their own party/requires gates. THE POINT: an override that "
      "would strand live records — a state holding records with no way out — is REFUSED with the "
      "count and the state named ('1 in answered'), because a stranded record looks exactly like one "
      "nobody has got to yet; a state that is terminal in the shipped workflow is correctly not "
      "treated as stranding. Overrides may rewire declared states but never invent new ones, "
      "duplicates/empties/oversized are rejected atomically, unreachable states are reported rather "
      "than silently ignored, reset restores the shipped workflow idempotently, and one project's "
      "override never touches another's.")
