"""GC portal engine test: module CRUD, role-gated workflow, change-order chain, pins,
activity timeline. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_modules.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_mod.db"
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ["AEC_RBAC"] = "1"  # enforce roles + party gates

for f in ("./test_mod.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402


def H(user):  # act as a given user (X-User identifies the party)
    return {"X-User": user}


with TestClient(app) as c:
    # module catalog loaded from module.json files
    mods = {m["key"]: m for m in c.get("/modules").json()}
    assert {"rfi", "submittal", "pco_request", "noc", "directive", "proposal", "cor", "eticket"} <= set(mods)

    # project created by GC (creator → admin + GC party)
    pid = c.post("/projects", json={"name": "Mega Tower"}, headers=H("gc")).json()["id"]
    # assign party roles
    for u, role, party in [("consultant", "reviewer", "Consultant"),
                           ("sub", "reviewer", "Subcontractor"),
                           ("owner", "reviewer", "Owner")]:
        r = c.post(f"/projects/{pid}/members", json={"user": u, "role": role, "party_role": party}, headers=H("gc"))
        assert r.status_code == 201, r.text

    # ---- RFI ball-in-court lifecycle, gated by party --------------------------
    rfi = c.post(f"/projects/{pid}/modules/rfi", headers=H("gc"), json={
        "data": {"subject": "Beam penetration at L3", "question": "OK to core the beam?", "discipline": "Structural"},
        "anchor": {"x": 12.0, "y": 4.5, "z": 7.6}, "element_guids": ["2UD3D7uxP8kecbbBCRtzEl"]}).json()
    assert rfi["ref"] == "RFI-001" and rfi["workflow_state"] == "draft"
    rid = rfi["id"]
    # GC submits
    assert c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", headers=H("gc"),
                  json={"action": "submit"}).json()["workflow_state"] == "open"
    # a subcontractor CANNOT answer an RFI (party gate) -> 403
    bad = c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", headers=H("sub"), json={"action": "respond"})
    assert bad.status_code == 403, bad.text
    # consultant answers
    assert c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", headers=H("consultant"),
                  json={"action": "respond"}).json()["workflow_state"] == "answered"
    # GC accepts -> closed
    assert c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", headers=H("gc"),
                  json={"action": "accept"}).json()["workflow_state"] == "closed"

    # ---- change-order chain across modules, with linking ---------------------
    pco = c.post(f"/projects/{pid}/modules/pco_request", headers=H("gc"),
                 json={"data": {"subject": "Added fireproofing", "description": "Owner-requested upgrade"},
                       "anchor": {"x": 1, "y": 2, "z": 3}}).json()
    c.post(f"/projects/{pid}/modules/pco_request/{pco['id']}/transition", headers=H("gc"), json={"action": "submit"})

    noc = c.post(f"/projects/{pid}/modules/noc", headers=H("gc"), json={"data": {"subject": "NOC: fireproofing"}}).json()
    # owner returns a direction
    noc = c.post(f"/projects/{pid}/modules/noc/{noc['id']}/transition", headers=H("owner"),
                 json={"action": "return_direction"}).json()
    assert noc["workflow_state"] == "returned"

    diru = c.post(f"/projects/{pid}/modules/directive", headers=H("gc"),
                  json={"data": {"subject": "Directive", "scope": "Apply 2hr fireproofing", "mode": "Pricing Only"}}).json()
    c.post(f"/projects/{pid}/modules/directive/{diru['id']}/transition", headers=H("sub"), json={"action": "acknowledge"})

    prop = c.post(f"/projects/{pid}/modules/proposal", headers=H("sub"),
                  json={"data": {"subject": "Fireproofing price", "amount": 48000}}).json()
    c.post(f"/projects/{pid}/modules/proposal/{prop['id']}/transition", headers=H("sub"), json={"action": "submit"})
    c.post(f"/projects/{pid}/modules/proposal/{prop['id']}/transition", headers=H("gc"), json={"action": "reconcile"})

    cor = c.post(f"/projects/{pid}/modules/cor", headers=H("gc"),
                 json={"data": {"subject": "COR: fireproofing", "amount": 52000, "schedule_days": 5},
                       "anchor": {"x": 1, "y": 2, "z": 3}}).json()
    c.post(f"/projects/{pid}/modules/cor/{cor['id']}/transition", headers=H("gc"), json={"action": "submit"})
    # owner approves
    cor = c.post(f"/projects/{pid}/modules/cor/{cor['id']}/transition", headers=H("owner"), json={"action": "approve"}).json()
    assert cor["workflow_state"] == "approved"

    # link the chain: COR -> proposal -> directive -> noc -> pco
    for tgt in [("proposal", prop["id"]), ("directive", diru["id"]), ("noc", noc["id"]), ("pco_request", pco["id"])]:
        c.post(f"/projects/{pid}/modules/cor/{cor['id']}/link", headers=H("gc"),
               json={"module": tgt[0], "id": tgt[1]})
    linked = c.get(f"/projects/{pid}/modules/cor/{cor['id']}", headers=H("gc")).json()
    assert len(linked["links"]) == 4

    # ---- model pins: anchored module records across modules ------------------
    pins = c.get(f"/projects/{pid}/module-pins", headers=H("gc")).json()
    refs = {p["ref"] for p in pins}
    assert "RFI-001" in refs and "PCO-001" in refs and "COR-001" in refs, refs
    assert all("anchor" in p and p["anchor"] for p in pins)

    # ---- activity timeline ---------------------------------------------------
    acts = [a["action"] for a in linked["activity"]]
    assert "create" in acts and any(a.startswith("transition:") for a in acts) and "link" in acts

    # ---- comments + CSV + PDF export (cross-cutting) -------------------------
    c.post(f"/projects/{pid}/modules/rfi/{rid}/comments", headers=H("consultant"),
           json={"text": "Coordinate with structural before coring."})
    rec = c.get(f"/projects/{pid}/modules/rfi/{rid}", headers=H("gc")).json()
    assert rec["comments"] and rec["comments"][0]["text"].startswith("Coordinate"), rec.get("comments")
    csv_text = c.get(f"/projects/{pid}/modules/cor/export.csv", headers=H("gc")).text
    assert "ref" in csv_text.splitlines()[0] and "COR-001" in csv_text, csv_text[:200]
    pdf = c.get(f"/projects/{pid}/modules/cor/{cor['id']}/pdf", headers=H("gc")).content
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1000, len(pdf)

    # ---- cross-module work queue (SQL-filtered: assigned OR party-actionable) -
    gc_work = c.get(f"/projects/{pid}/my-work", headers=H("gc")).json()
    assert gc_work and all(w["reason"] in ("assigned", "ball-in-court") for w in gc_work), gc_work
    assert all({"module", "ref", "state"} <= set(w) for w in gc_work)
    # a user with no membership/party sees nothing actionable and nothing assigned to them
    assert c.get(f"/projects/{pid}/my-work", headers=H("nobody")).json() == []

    # ---- email digests: per-member work-queue summaries ----------------------
    # register gc as an account (first user → admin) and give it an email
    assert c.post("/auth/register", json={"username": "gc", "password": "gcpassword"}).status_code == 201
    assert c.patch("/auth/users/gc", json={"email": "gc@example.com"}, headers=H("gc")).json()["email"] == "gc@example.com"
    # preview: gc has open items (GC party is ball-in-court on the chain); SMTP off in tests
    pv = c.get(f"/projects/{pid}/notifications/digest/preview", headers=H("gc")).json()
    assert pv["smtp_configured"] is False
    gc_dig = next((r for r in pv["recipients"] if r["user"] == "gc"), None)
    assert gc_dig and gc_dig["count"] > 0 and "open item" in gc_dig["text"], pv
    # send: gc has an email → attempted (status 'disabled', no SMTP); members w/o email skipped
    res = c.post(f"/projects/{pid}/notifications/digest", headers=H("gc")).json()
    assert res["smtp_configured"] is False
    assert "gc" in res["results"].get("disabled", []), res     # has email → attempted (disabled, no SMTP)
    assert "gc" not in res["skipped_no_email"], res
    # non-admin can't trigger a digest
    assert c.post(f"/projects/{pid}/notifications/digest", headers=H("sub")).status_code == 403

    print("GC MODULES OK")
    print(f"  modules loaded: {len(mods)}  |  project={pid}")
    print(f"  RFI lifecycle gated (sub blocked from answering: 403)")
    print(f"  change-order chain: PCO->NOC->DIR->PROP->COR (approved, {len(linked['links'])} links)")
    print(f"  model pins: {sorted(refs)}")
