"""Data-source connections (admin). Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_connections.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./conn_test.db"
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ.pop("AEC_RBAC", None)
for f in ("./conn_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

with TestClient(app) as c:
    assert c.get("/connections").status_code == 403                      # admin-gated
    tok = c.post("/auth/register", json={"username": "admin", "password": "supersecret"}).json()
    tok = c.post("/auth/login", json={"username": "admin", "password": "supersecret"}).json()["token"]

    # built-in local DB appears with a live OK status + table count
    lst = c.get("/connections", headers=BEARER(tok)).json()
    assert "procore" in lst["types"] and "supabase" in lst["types"]
    local = next(x for x in lst["connections"] if x["id"] == "local")
    assert local["builtin"] and local["status"]["ok"] and "table" in local["status"]["detail"], local

    # register a Postgres connection — DSN password is masked on read
    pg = c.post("/connections", headers=BEARER(tok),
                json={"name": "Reporting DB", "type": "postgres",
                      "config": {"dsn": "postgresql://user:secretpw@db.example.com:5432/reports"}}).json()
    assert "***" in pg["config"]["dsn"] and "secretpw" not in pg["config"]["dsn"], pg["config"]
    # testing it fails gracefully (host unreachable) — no exception
    t = c.post(f"/connections/{pg['id']}/test", headers=BEARER(tok)).json()
    assert t["status"]["ok"] is False and t["status"]["detail"], t

    # Supabase is a Postgres DSN; Procore is token-based — secret never echoed
    proc = c.post("/connections", headers=BEARER(tok),
                  json={"name": "Procore", "type": "procore", "config": {"access_token": "tok-123"}}).json()
    assert proc["config"].get("access_token_set") is True and "access_token" not in proc["config"], proc["config"]

    # ad-hoc test of the local type (used by the add form)
    assert c.post("/connections/test", headers=BEARER(tok), json={"type": "local", "config": {}}).json()["ok"]

    # update keeps the secret when the form re-sends it blank
    upd = c.put(f"/connections/{proc['id']}", headers=BEARER(tok),
                json={"name": "Procore (prod)", "type": "procore", "config": {"access_token": ""}}).json()
    assert upd["name"] == "Procore (prod)" and upd["config"]["access_token_set"] is True

    # validation: 'local' can't be created; unknown type rejected
    assert c.post("/connections", headers=BEARER(tok), json={"name": "x", "type": "local"}).status_code == 400
    assert c.post("/connections", headers=BEARER(tok), json={"name": "x", "type": "mysql"}).status_code == 400

    # delete
    assert c.delete(f"/connections/{pg['id']}", headers=BEARER(tok)).json()["ok"]
    ids = {x["id"] for x in c.get("/connections", headers=BEARER(tok)).json()["connections"]}
    assert pg["id"] not in ids and proc["id"] in ids

    # --- data plane: read-only browse / query on the local app DB --------------
    tbls = c.get("/connections/local/tables", headers=BEARER(tok)).json()
    assert tbls["kind"] == "sql" and "users" in tbls["tables"], tbls
    # a real SELECT returns rows (we registered users above)
    q = c.post("/connections/local/query", headers=BEARER(tok),
               json={"sql": "SELECT username, role FROM users", "limit": 50}).json()
    assert "username" in q["columns"] and q["row_count"] >= 1, q
    # the LIMIT is enforced even if the query omits it
    q2 = c.post("/connections/local/query", headers=BEARER(tok),
                json={"sql": "SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3", "limit": 2}).json()
    assert q2["row_count"] == 2, q2
    # security: writes / DDL / multiple statements are rejected
    for bad in ("DELETE FROM users", "DROP TABLE users", "UPDATE users SET role='admin'",
                "SELECT 1; DROP TABLE users", "INSERT INTO users VALUES ('x')"):
        r = c.post("/connections/local/query", headers=BEARER(tok), json={"sql": bad}).json()
        assert "error" in r and "rows" not in r, (bad, r)
    assert c.post("/connections/local/query", headers=BEARER(tok),
                  json={"sql": "SELECT 1"}).status_code == 200
    # data-plane is admin-gated too (clear the login cookie so the request is truly unauthenticated)
    c.cookies.clear()
    assert c.get("/connections/local/tables").status_code == 403

    # --- Procore → module sync: RFIs + submittals + change events (idempotent) --
    from aec_api import connectors as _conn
    _conn.procore_rfis = lambda token, ppid: [
        {"id": 101, "number": "1", "subject": "Beam penetration", "questions": [{"body": "OK to core?"}]},
        {"id": 102, "number": "2", "subject": "Slab edge", "body": "Confirm dimension?"}]
    _conn.procore_submittals = lambda token, ppid: [
        {"id": 201, "number": "S-1", "title": "Rebar shop drawings", "specification_section": "03 20 00",
         "type": "Shop Drawing", "status": "Open"}]
    _conn.procore_change_events = lambda token, ppid: [
        {"id": 301, "number": "CE-1", "title": "Added fireproofing",
         "change_event_line_items": [{"amount": 12000}, {"amount": 3000}]}]
    pc = c.post("/connections", headers=BEARER(tok),
                json={"name": "Procore sync", "type": "procore", "config": {"access_token": "tok-xyz"}}).json()
    proj = c.post("/projects", json={"name": "Sync Target"}).json()["id"]
    s1 = c.post(f"/projects/{proj}/sync/procore", headers=BEARER(tok),
                json={"connection_id": pc["id"], "procore_project_id": "9999"}).json()
    assert s1["imported_total"] == 4, s1                                              # 2 rfi + 1 sub + 1 ce
    assert s1["results"]["rfi"]["imported"] == 2 and s1["results"]["submittal"]["imported"] == 1
    assert s1["results"]["change_event"]["imported"] == 1, s1["results"]
    # mappings landed in the right modules
    assert any("core" in (x["data"].get("question") or "") for x in c.get(f"/projects/{proj}/modules/rfi").json())
    subs = c.get(f"/projects/{proj}/modules/submittal").json()
    assert subs[0]["data"]["spec_section"] == "03 20 00" and subs[0]["data"]["procore_id"] == "201", subs
    ces = c.get(f"/projects/{proj}/modules/change_event").json()
    assert ces[0]["data"]["rom"] == 15000.0, ces                                      # summed line items
    # idempotent re-run
    s2 = c.post(f"/projects/{proj}/sync/procore", headers=BEARER(tok),
                json={"connection_id": pc["id"], "procore_project_id": "9999"}).json()
    assert s2["imported_total"] == 0, s2
    # a non-Procore connection can't be used for the Procore sync
    assert c.post(f"/projects/{proj}/sync/procore", headers=BEARER(tok),
                  json={"connection_id": "local", "procore_project_id": "1"}).status_code in (400, 404)

    # --- field-mapping editor: admins remap Procore source paths per field -----
    mp = c.get(f"/connections/{pc['id']}/mappings", headers=BEARER(tok)).json()["mappings"]
    rfi_fields = {f["field"]: f for f in mp["rfi"]["fields"]}
    assert rfi_fields["subject"]["default"] == "subject", rfi_fields           # editable + carries default
    assert rfi_fields["question"]["path"] == "questions.0.body"                # no override yet -> default
    assert mp["rfi"]["module"] == "rfi" and "submittal" in mp and "change_event" in mp, mp
    # override: pull the RFI subject from the Procore 'number' field instead
    assert c.put(f"/connections/{pc['id']}/mappings", headers=BEARER(tok),
                 json={"mappings": {"rfi": {"subject": "number"}}}).json()["ok"]
    got = c.get(f"/connections/{pc['id']}/mappings", headers=BEARER(tok)).json()["mappings"]
    assert {f["field"]: f["path"] for f in got["rfi"]["fields"]}["subject"] == "number"
    # a fresh project sync now applies the override (subject := Procore number)
    proj2 = c.post("/projects", json={"name": "Remapped"}).json()["id"]
    sm = c.post(f"/projects/{proj2}/sync/procore", headers=BEARER(tok),
                json={"connection_id": pc["id"], "procore_project_id": "9999", "kinds": ["rfi"]}).json()
    assert sm["results"]["rfi"]["imported"] == 2, sm
    subjects = {x["data"]["subject"] for x in c.get(f"/projects/{proj2}/modules/rfi").json()}
    assert subjects == {"1", "2"}, subjects                                    # remapped, not "Beam penetration"
    # clear the override so the rest of the suite uses defaults
    assert c.put(f"/connections/{pc['id']}/mappings", headers=BEARER(tok), json={"mappings": {}}).json()["ok"]
    # field mapping is a Procore-only concept
    assert c.get("/connections/local/mappings", headers=BEARER(tok)).status_code == 400

    # --- scheduled / auto-sync ------------------------------------------------
    sch = c.post(f"/projects/{proj}/sync/schedules", headers=BEARER(tok),
                 json={"connection_id": pc["id"], "procore_project_id": "9999", "kinds": ["rfi"],
                       "interval_minutes": 30}).json()
    assert sch["enabled"] and sch["interval_minutes"] == 30 and sch["last_run"] is None
    # run_due imports nothing new (already synced) but stamps last_run + last_result
    from aec_api import sync as _sync
    from aec_api.db import SessionLocal as _SL
    with _SL() as _db:
        ran = _sync.run_due(_db)
    assert any(r["schedule_id"] == sch["id"] for r in ran), ran
    after = next(x for x in c.get(f"/projects/{proj}/sync/schedules", headers=BEARER(tok)).json() if x["id"] == sch["id"])
    assert after["last_run"] is not None and after["last_result"]["imported_total"] == 0, after
    # a second run_due immediately is NOT due (interval not elapsed)
    with _SL() as _db:
        assert _sync.run_due(_db) == []
    # two-way schedule flag round-trips
    sch2 = c.post(f"/projects/{proj}/sync/schedules", headers=BEARER(tok),
                  json={"connection_id": pc["id"], "procore_project_id": "9999", "push": True}).json()
    assert sch2["push"] is True
    assert c.put(f"/projects/{proj}/sync/schedules/{sch2['id']}", headers=BEARER(tok),
                 json={"push": False}).json()["push"] is False
    c.delete(f"/projects/{proj}/sync/schedules/{sch2['id']}", headers=BEARER(tok))
    # disable + delete
    assert c.put(f"/projects/{proj}/sync/schedules/{sch['id']}", headers=BEARER(tok),
                 json={"enabled": False}).json()["enabled"] is False
    assert c.delete(f"/projects/{proj}/sync/schedules/{sch['id']}", headers=BEARER(tok)).json()["ok"]

    # --- two-way: push a resolved RFI back to Procore (stubbed write) -----------
    pushes: list = []
    _conn.procore_update_rfi = lambda token, ppid, rid, payload: pushes.append((rid, payload)) or {}
    rfis = c.get(f"/projects/{proj}/modules/rfi").json()
    rid = rfis[0]["id"]
    pext = rfis[0]["data"]["procore_id"]
    c.post(f"/projects/{proj}/modules/rfi/{rid}/transition", headers=BEARER(tok), json={"action": "submit"})   # draft->open
    c.patch(f"/projects/{proj}/modules/rfi/{rid}", headers=BEARER(tok), json={"answer": "Yes, proceed."})
    c.post(f"/projects/{proj}/modules/rfi/{rid}/transition", headers=BEARER(tok), json={"action": "respond"})  # open->answered
    p1 = c.post(f"/projects/{proj}/sync/procore/push", headers=BEARER(tok),
                json={"connection_id": pc["id"], "procore_project_id": "9999", "kinds": ["rfi"]}).json()
    assert p1["pushed_total"] == 1 and len(pushes) == 1, (p1, pushes)
    assert pushes[0][0] == pext and pushes[0][1]["answer"] == "Yes, proceed." and pushes[0][1]["status"] == "open", pushes
    # idempotent (already pushed this state) + the still-draft RFI is never pushed
    p2 = c.post(f"/projects/{proj}/sync/procore/push", headers=BEARER(tok),
                json={"connection_id": pc["id"], "procore_project_id": "9999"}).json()
    assert p2["pushed_total"] == 0 and len(pushes) == 1, (p2, pushes)
    assert c.post(f"/projects/{proj}/sync/procore/push", headers=BEARER(tok),
                  json={"connection_id": "local", "procore_project_id": "1"}).status_code in (400, 404)

    # --- Autodesk Construction Cloud (ACC): same adapter pattern (token + project/issue read) --
    assert "acc" in c.get("/connections", headers=BEARER(tok)).json()["types"]
    _conn._aps_get = lambda path, token: {"userName": "jane.doe", "emailId": "jane@firm.com"}  # /me
    _conn.acc_projects = lambda token, account: [{"id": "p1", "name": "Tower A"}, {"id": "p2", "name": "Garage"}]
    _conn.acc_issues = lambda token, pid: [{"id": "i1", "title": "Cracked slab", "status": "open"}]
    acc = c.post("/connections", headers=BEARER(tok),
                 json={"name": "ACC", "type": "acc",
                       "config": {"access_token": "aps-tok", "account_id": "acct-1"}}).json()
    assert acc["config"].get("access_token_set") is True and acc["config"].get("account_id") == "acct-1", acc["config"]
    at = c.post(f"/connections/{acc['id']}/test", headers=BEARER(tok)).json()
    assert at["status"]["ok"] and "jane.doe" in at["status"]["detail"], at                # token validated via /me
    assert at["info"]["project_count"] == 2 and "Tower A" in at["info"]["projects"], at["info"]
    accb = c.get(f"/connections/{acc['id']}/tables", headers=BEARER(tok)).json()
    assert accb["kind"] == "acc" and accb["project_count"] == 2, accb                     # browse -> projects
    iss = c.get(f"/connections/{acc['id']}/acc/projects/p1/issues", headers=BEARER(tok)).json()
    assert iss["kind"] == "acc-issues" and iss["count"] == 1 and iss["issues"][0]["title"] == "Cracked slab", iss
    # issues browse is an ACC-only concept
    assert c.get(f"/connections/{pc['id']}/acc/projects/p1/issues", headers=BEARER(tok)).status_code == 400

    # --- QuickBooks (accounting/ERP): same adapter pattern (token+realm, read the books) --
    assert "quickbooks" in c.get("/connections", headers=BEARER(tok)).json()["types"]
    _conn._qb_get = lambda path, token: {"CompanyInfo": {"CompanyName": "Acme Builders"}}  # companyinfo
    _conn.qb_accounts = lambda token, realm: [{"Name": "Cost of Goods Sold"}, {"Name": "Job Materials"}]
    _conn.qb_bills = lambda token, realm: [{"Id": "1", "TotalAmt": 4200.0}]
    qb = c.post("/connections", headers=BEARER(tok),
                json={"name": "QBO", "type": "quickbooks",
                      "config": {"access_token": "qb-tok", "realm_id": "9130350"}}).json()
    assert qb["config"].get("access_token_set") is True and qb["config"].get("realm_id") == "9130350", qb["config"]
    qt = c.post(f"/connections/{qb['id']}/test", headers=BEARER(tok)).json()
    assert qt["status"]["ok"] and "Acme Builders" in qt["status"]["detail"], qt
    assert qt["info"]["account_count"] == 2, qt["info"]
    qbb = c.get(f"/connections/{qb['id']}/tables", headers=BEARER(tok)).json()
    assert qbb["kind"] == "quickbooks" and qbb["account_count"] == 2, qbb
    bills = c.get(f"/connections/{qb['id']}/quickbooks/bills", headers=BEARER(tok)).json()
    assert bills["kind"] == "quickbooks-bills" and bills["count"] == 1, bills
    assert c.get(f"/connections/{qb['id']}/quickbooks/widgets", headers=BEARER(tok)).status_code == 400  # bad entity

    # --- Sage / Viewpoint (generic REST ERP): same shape, configurable base_url --
    assert "sage" in c.get("/connections", headers=BEARER(tok)).json()["types"]
    _conn.erp_read = lambda cfg, entity: [{"name": "1000 Cash"}, {"name": "5000 COGS"}] if entity == "accounts" else [{"id": "b1"}]
    sg = c.post("/connections", headers=BEARER(tok),
                json={"name": "Sage", "type": "sage",
                      "config": {"access_token": "sage-tok", "base_url": "https://api.sage.example.com"}}).json()
    assert sg["config"].get("access_token_set") is True and sg["config"].get("base_url"), sg["config"]
    st = c.post(f"/connections/{sg['id']}/test", headers=BEARER(tok)).json()
    assert st["status"]["ok"] and "2 accounts" in st["status"]["detail"], st
    erp = c.get(f"/connections/{sg['id']}/erp/bills", headers=BEARER(tok)).json()
    assert erp["kind"] == "sage-bills" and erp["count"] == 1, erp
    assert c.get(f"/connections/{sg['id']}/erp/nope", headers=BEARER(tok)).status_code == 400  # bad entity

    print("CONNECTIONS OK - status, masked secrets, test, CRUD, validation, read-only browse/query, "
          "Procore->rfi/submittal/change_event sync (idempotent), field-mapping editor, "
          "auto-sync schedules + run_due, two-way push, ACC + QuickBooks + Sage/Viewpoint read")
