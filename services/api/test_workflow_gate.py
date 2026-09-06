"""Transition field-gating: a workflow transition declaring `requires: [field]` is blocked until
those fields are filled (RFI can't be Answered without an answer; COR can't be Approved without an
amount). Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_workflow_gate.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_wfgate.db"
os.environ["STORAGE_DIR"] = "./test_storage_wfgate"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_wfgate.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()["id"]


def trans(c, pid, key, rid, action):
    return c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Gate"}).json()["id"]

    # --- RFI: respond (open -> answered) requires an `answer` ------------------
    rid = mk(c, pid, "rfi", {"subject": "Beam size?", "question": "What size is the transfer beam?"})
    assert trans(c, pid, "rfi", rid, "submit").json()["workflow_state"] == "open"
    blocked = trans(c, pid, "rfi", rid, "respond")
    assert blocked.status_code == 400 and ("answer" in blocked.json()["detail"].lower() or "response" in blocked.json()["detail"].lower()), blocked.text[:160]
    # available_actions advertises the requirement so the UI can show it
    rec = c.get(f"/projects/{pid}/modules/rfi/{rid}").json()
    acts = {a["action"]: a.get("requires", []) for a in rec.get("available_actions", [])}
    assert acts.get("respond") == ["answer"], acts
    # fill the answer → the transition now passes
    c.patch(f"/projects/{pid}/modules/rfi/{rid}", json={"answer": "W24x76"})
    ok = trans(c, pid, "rfi", rid, "respond")
    assert ok.status_code == 200 and ok.json()["workflow_state"] == "answered", ok.text[:160]

    # the gate is generic (any manifest can declare `requires` on a transition); a transition with
    # no `requires` is unaffected — RFI submit (draft -> open) needs nothing and passes.
    rid2 = mk(c, pid, "rfi", {"subject": "Door schedule?", "question": "Confirm hardware set."})
    assert trans(c, pid, "rfi", rid2, "submit").status_code == 200

    # --- ALTERNATIVES: `requires: ["a|b"]` is met by EITHER ---------------------------------------
    #
    # Found by review on PR #449. The MOD-SWEEP additive pattern adds a reference field BESIDE its
    # text field and retires the text later — so `entitlement.agency_company` arrived carrying help
    # text that tells the user to pick a company INSTEAD of typing the agency name, while `submit`
    # still required the typed `agency`. A linked-only entitlement could never be submitted: the new
    # control was a trap, and the PR that added it created the trap.
    #
    # Asserted at the ROUTE, because the value of this rule is entirely in what the engine refuses.
    ent = mk(c, pid, "entitlement", {"subject": "CUP for the podium",
                                     "application_type": "Conditional Use Permit"})
    empty = trans(c, pid, "entitlement", ent, "submit")
    assert empty.status_code == 400, ("neither half filled must still be refused — the gate is "
                                      "loosened, not removed", empty.text[:200])
    assert "agency" in empty.json()["detail"].lower(), empty.text[:200]
    # the reference alone satisfies it — the case that was impossible before
    co = c.post(f"/projects/{pid}/modules/company", json={"data": {"name": "City of Example",
                                                                  "type": "Authority"}}).json()
    c.patch(f"/projects/{pid}/modules/entitlement/{ent}", json={"agency_company": co["id"]})
    linked = trans(c, pid, "entitlement", ent, "submit")
    assert linked.status_code == 200 and linked.json()["workflow_state"] == "submitted", linked.text[:200]

    # and the TEXT alone still satisfies it, because every existing record has only that. A fix that
    # moved the requirement to the reference would strand them all — this is the back-compat half.
    ent2 = mk(c, pid, "entitlement", {"subject": "Variance", "application_type": "Variance",
                                      "agency": "City of Example"})
    typed = trans(c, pid, "entitlement", ent2, "submit")
    assert typed.status_code == 200 and typed.json()["workflow_state"] == "submitted", typed.text[:200]

print("WORKFLOW-GATE OK - RFI respond blocked without an answer (400); available_actions advertises "
      "`requires`; passes once filled; transitions without `requires` are unaffected. An entry naming "
      "ALTERNATIVES (`agency|agency_company`) is met by EITHER half and by neither being absent: the "
      "reference alone submits (the case the additive pattern made impossible), the typed text alone "
      "still submits (every pre-existing record has only that), and an empty record is still refused.")
