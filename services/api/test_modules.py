"""GC portal engine test: module CRUD, role-gated workflow, change-order chain, pins,
activity timeline. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_modules.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_mod.db"
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ["AEC_RBAC"] = "1"  # enforce roles + party gates
os.environ["AEC_TRUST_XUSER"] = "1"  # tests act as users via X-User

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
    # /modules exposes title_field (the web uses it for inline "add new" from reference dropdowns)
    assert mods["cost_code"]["title_field"] == "code", mods["cost_code"].get("title_field")
    # X1: cost-impacting modules carry a cost_code reference so impacts roll to the budget
    for k in ("rfi", "cor", "change_event", "pco_request", "proposal", "submittal"):
        refs = [f for f in mods[k]["fields"] if f.get("type") == "reference" and f.get("module") == "cost_code"]
        assert refs, f"{k} should reference cost_code"

    # Tier-1 field completeness (super + PM field set, benchmarked to Procore/Fieldwire)
    def fnames(k):
        return {f["name"] for f in mods[k]["fields"]}
    # daily_report — the super's #1 tool: weather impact, equipment, delays, visitors, safety, photos
    assert {"temp_f", "weather_impact", "equipment_on_site", "delays", "visitors", "safety_note", "photos"} <= fnames("daily_report")
    # the daily-report location/weather selects are enum-driven (not free text)
    wf = next(f for f in mods["daily_report"]["fields"] if f["name"] == "weather")
    assert wf["type"] == "select" and "Rain" in wf["options"], wf
    # rfi — priority + location reference + manager/asked-by
    assert {"priority", "location", "rfi_manager", "received_from"} <= fnames("rfi")
    assert any(f["name"] == "location" and f.get("module") == "location" for f in mods["rfi"]["fields"])
    # submittal — revision, lead/required-on-site/received/returned dates, responsible contractor
    assert {"rev", "required_on_site", "date_received", "date_returned", "responsible_contractor"} <= fnames("submittal")
    # cor / change_event / pco — reason + schedule impact + received_from
    assert {"reason", "received_from"} <= fnames("cor")
    assert {"reason", "scope_status", "schedule_impact_days"} <= fnames("change_event")
    assert {"schedule_impact_days", "received_from"} <= fnames("pco_request")
    # punchlist + inspection — verification + photos + re-inspection
    assert {"verified_by", "photos"} <= fnames("punchlist")
    assert {"reinspection_date", "photos"} <= fnames("inspection")

    # F1: tier-1 forms group fields into labeled fieldsets, and each fieldset is a single
    # contiguous run (the web renderer emits one header per run — non-contiguous would duplicate).
    for k in ("rfi", "submittal", "daily_report", "cor", "change_event", "pco_request", "punchlist",
              "inspection", "incident", "meeting", "subcontract", "prime_contract", "commitment"):
        seq = [f.get("fieldset") for f in mods[k]["fields"] if f["type"] != "rollup"]
        assert all(seq), f"{k}: every form field should have a fieldset, got {seq}"
        runs = [fs for i, fs in enumerate(seq) if i == 0 or fs != seq[i - 1]]
        assert len(runs) == len(set(runs)), f"{k}: fieldsets must be contiguous, got {runs}"

    # Tier-2 field depth (safety OSHA log, meeting minutes, subcontract retainage/compliance)
    assert {"injured_person", "body_part", "injury_type", "osha_recordable", "root_cause",
            "corrective_action", "photos"} <= fnames("incident")
    assert {"agenda", "attendees", "next_meeting", "distribution"} <= fnames("meeting")
    assert {"scope", "retainage_pct", "executed_date", "insurance_exp", "cost_code"} <= fnames("subcontract")
    assert {"owner", "executed_date", "retainage_pct", "substantial_completion", "ld_per_day"} <= fnames("prime_contract")
    assert {"type", "po_date", "retainage_pct"} <= fnames("commitment")
    # compliance modules use the canonical `expires` date (warranty/COBie convention), never a
    # duplicate `expiry`. Lock that out everywhere so the alert logic keys off one field.
    assert {"coverage_type", "expires", "additional_insured"} <= fnames("coi") and "expiry" not in fnames("coi")
    assert {"permit_type", "status", "expires", "issued_date"} <= fnames("permit") and "expiry" not in fnames("permit")
    for k, m in mods.items():
        nm = {f["name"] for f in m["fields"]}
        assert not ({"expires", "expiry"} <= nm), f"{k} has both expires+expiry (duplicate date field)"

    # C1: the web "convert to…" map relies on a back-reference field on each target module so the
    # new record links to its source. Lock those reference fields so the map can't silently break.
    def has_ref(mod, field, target):
        return any(f["name"] == field and f.get("type") == "reference" and f.get("module") == target
                   for f in mods[mod]["fields"])
    assert has_ref("change_event", "source_rfi", "rfi"), "RFI→Change Event needs change_event.source_rfi"
    assert has_ref("pco_request", "source_rfi", "rfi"), "RFI→PCO needs pco_request.source_rfi"
    assert has_ref("punchlist", "observation", "observation"), "Observation→Punch needs punchlist.observation"
    assert has_ref("deficiency", "inspection", "inspection"), "Inspection→Deficiency needs deficiency.inspection"
    assert has_ref("ncr", "inspection", "inspection"), "Inspection→NCR needs ncr.inspection"

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

    # ---- newly-wired cross-module relations -----------------------------------
    # meetings → action items (reverse rollup count + related)
    mtg = c.post(f"/projects/{pid}/modules/meeting", headers=H("gc"), json={"data": {"subject": "OAC #3"}}).json()
    for s in ("Resolve curtain-wall detail", "Confirm long-lead steel"):
        c.post(f"/projects/{pid}/modules/action_item", headers=H("gc"),
               json={"data": {"subject": s, "meeting": mtg["id"]}})
    mtg = c.get(f"/projects/{pid}/modules/meeting/{mtg['id']}", headers=H("gc")).json()
    assert mtg["data"]["action_count"] == 2, mtg["data"]
    rel = c.get(f"/projects/{pid}/modules/meeting/{mtg['id']}/related", headers=H("gc")).json()
    assert any(r.get("module") == "action_item" for r in rel.get("incoming", [])), rel
    # change orders → subcontract ($ rollup of linked CORs)
    sub = c.post(f"/projects/{pid}/modules/subcontract", headers=H("gc"), json={"data": {"vendor": "ACME Steel"}}).json()
    for amt in (12000, 8000):
        c.post(f"/projects/{pid}/modules/cor", headers=H("gc"),
               json={"data": {"subject": f"CO {amt}", "amount": amt, "subcontract": sub["id"]}})
    sub = c.get(f"/projects/{pid}/modules/subcontract/{sub['id']}", headers=H("gc")).json()
    assert sub["data"]["change_orders"] == 20000, sub["data"]
    # rfi → drawing reference resolves to a clickable brief
    dwg = c.post(f"/projects/{pid}/modules/drawing", headers=H("gc"), json={"data": {"number": "A-101"}}).json()
    rfi2 = c.post(f"/projects/{pid}/modules/rfi", headers=H("gc"),
                  json={"data": {"subject": "Detail at A-101", "question": "?", "drawing": dwg["id"]}}).json()
    rfi2 = c.get(f"/projects/{pid}/modules/rfi/{rfi2['id']}", headers=H("gc")).json()
    assert rfi2["data_refs"].get("drawing", {}).get("id") == dwg["id"], rfi2.get("data_refs")

    # ---- revisions (engine feature; revisable modules only) -------------------
    rev = c.post(f"/projects/{pid}/modules/rfi/{rid}/revise", headers=H("gc"))
    assert rev.status_code == 201, rev.text
    rev = rev.json()
    assert rev["ref"] == "RFI-001.1" and rev["data"]["revision"] == 1, rev["ref"]
    assert rev["workflow_state"] == "draft"                       # re-opened at the initial state
    assert rev["revision"]["revises"]["ref"] == "RFI-001", rev["revision"]
    src = c.get(f"/projects/{pid}/modules/rfi/{rid}", headers=H("gc")).json()
    assert src["revision"]["superseded_by"]["ref"] == "RFI-001.1", src["revision"]
    # the superseded original can't be revised again; the revision chains to .2
    assert c.post(f"/projects/{pid}/modules/rfi/{rid}/revise", headers=H("gc")).status_code == 409
    rev2 = c.post(f"/projects/{pid}/modules/rfi/{rev['id']}/revise", headers=H("gc")).json()
    assert rev2["ref"] == "RFI-001.2" and rev2["data"]["revision"] == 2, rev2["ref"]
    # non-revisable modules reject (the flag is checked before record lookup)
    assert c.post(f"/projects/{pid}/modules/daily_report/none/revise", headers=H("gc")).status_code == 400
    # the catalog advertises which modules are revisable
    cat = {m["key"]: m for m in c.get("/modules").json()}
    assert cat["rfi"]["revisable"] is True and cat["daily_report"]["revisable"] is False
    # controlled Documents register: a config-only module that's revisable (version history) + attachments
    assert cat.get("document", {}).get("revisable") is True, "document module should load + be revisable"
    doc = c.post(f"/projects/{pid}/modules/document", headers=H("gc"), json={"data": {"title": "Spec 03 30 00", "doc_type": "Specification"}}).json()
    docrev = c.post(f"/projects/{pid}/modules/document/{doc['id']}/revise", headers=H("gc")).json()
    assert docrev["ref"] == "DOC-001.1", docrev.get("ref")

    # ---- AI Draft RFI (template fallback when no ANTHROPIC_API_KEY) -----------
    d = c.post(f"/projects/{pid}/ai/draft-rfi", headers=H("gc"), json={
        "element": {"ifc_class": "IfcBeam", "name": "B-12", "storey": "Level 3"},
        "note": "Is it OK to core a 50mm penetration?"}).json()
    assert d["ai_enabled"] is False and d["source"] == "template", d
    assert "B-12" in d["subject"] and d["question"] and d["discipline"] == "Structural"
    assert d["suggested_priority"] in ("low", "normal", "high", "urgent")
    # reviewer-gated: a party-less / no-role user can't draft
    assert c.post(f"/projects/{pid}/ai/draft-rfi", headers=H("nobody"), json={"element": {}}).status_code == 403

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

    # ---- E1: project-level custom enum options (extend a select without editing JSON) --------
    assert c.get(f"/projects/{pid}/enum-options", headers=H("gc")).json() == {}  # none yet
    add = c.post(f"/projects/{pid}/modules/rfi/enum/discipline", headers=H("gc"),
                 json={"value": "Acoustics"})
    assert add.status_code == 201 and "Acoustics" in add.json()["options"], add.text
    # it now shows up in the per-project catalog, nested module→field→[values]
    opts = c.get(f"/projects/{pid}/enum-options", headers=H("gc")).json()
    assert opts.get("rfi", {}).get("discipline") == ["Acoustics"], opts
    # idempotent: re-adding the same value (or a JSON built-in) doesn't duplicate
    c.post(f"/projects/{pid}/modules/rfi/enum/discipline", headers=H("gc"), json={"value": "Acoustics"})
    c.post(f"/projects/{pid}/modules/rfi/enum/discipline", headers=H("gc"), json={"value": "Structural"})
    opts = c.get(f"/projects/{pid}/enum-options", headers=H("gc")).json()
    assert opts["rfi"]["discipline"] == ["Acoustics"], opts
    # a record can be created using the custom value
    r2 = c.post(f"/projects/{pid}/modules/rfi", headers=H("gc"),
                json={"data": {"subject": "Acoustic RFI", "question": "STC?", "discipline": "Acoustics"}})
    assert r2.json()["data"]["discipline"] == "Acoustics", r2.text
    # validation: only select/multiselect fields accept custom options
    assert c.post(f"/projects/{pid}/modules/rfi/enum/subject", headers=H("gc"),
                  json={"value": "x"}).status_code == 422
    assert c.post(f"/projects/{pid}/modules/rfi/enum/discipline", headers=H("gc"),
                  json={"value": "   "}).status_code == 422

    print("GC MODULES OK")
    print(f"  modules loaded: {len(mods)}  |  project={pid}")
    print(f"  RFI lifecycle gated (sub blocked from answering: 403)")
    print(f"  change-order chain: PCO->NOC->DIR->PROP->COR (approved, {len(linked['links'])} links)")
    print(f"  model pins: {sorted(refs)}")
