"""R23-JURISDICTION-PACKS over HTTP — the pack library, and a project's check against its place.

The engine is tested in `test_jurisdiction_packs.py`. What only a live app shows is the resolution
from `Project.jurisdiction` — the field already existed and drove code editions, and nothing read it
for data requirements. The assertion that matters: a project with no jurisdiction gets nothing and a
reason, never a default pack.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_jurisdiction_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_juris_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_juris_route"
os.environ.pop("AEC_RBAC", None)
# Importing/deleting a pack is now platform-admin only — the routes are GLOBAL, and a pack changes
# compliance results across every project in a matching jurisdiction. `require_admin_user` resolves
# admins from AEC_ADMIN_EMAILS, so the harness declares its caller one rather than reaching past the
# gate. (The gate itself is proved by test_jurisdiction_authz, which runs with RBAC ON.)
os.environ["AEC_ADMIN_EMAILS"] = "juris@test"
for _f in ("./test_juris_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import model_index  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


PACK = {
    "id": "tx-example-city", "jurisdiction": "TX",
    "authority": "Example City Building Department",
    "name": "Model submission data requirements", "edition": "2026",
    "source": "https://example.gov/bim-submission-standard-2026.pdf",
    "requirements": [
        {"id": "walls-rated", "name": "Walls declare a fire rating", "scope": "IfcWall",
         "require": "Pset_WallCommon::FireRating", "severity": "high"},
    ],
}

ELEMENTS = [
    {"guid": "w1", "ifc_class": "IfcWall", "name": "W1",
     "psets": {"Pset_WallCommon": {"FireRating": "1HR"}}, "qtos": {}},
    {"guid": "w2", "ifc_class": "IfcWall", "name": "W2", "psets": {}, "qtos": {}},
]

with TestClient(app) as c:
    c.headers.update({"X-User": "juris@test"})
    # require_admin_user looks the caller up in the users table, so the row has to exist.
    from aec_api.db import SessionLocal
    from aec_api.models import User
    with SessionLocal() as _db:
        if not _db.get(User, "juris@test"):
            _db.add(User(username="juris@test", password_hash="", role="admin", active=True))
            _db.commit()

    lib = c.get("/jurisdiction/packs")
    check("GET /jurisdiction/packs answers 200", lib.status_code == 200, lib.text[:200])
    L = lib.json()
    check("  it ships exactly one built-in", L["count"] == 1, L["count"])
    check("  flagged as an example, attributed to nobody real",
          L["packs"][0]["is_example"] is True and "example" in L["packs"][0]["authority"].lower())

    bad = c.post("/jurisdiction/packs", json={**PACK, "authority": ""})
    check("a pack with no authority is a 422", bad.status_code == 422, bad.status_code)
    check("  and the response says why a citation is required",
          "house rule" in bad.text or "look up why" in bad.text, bad.text[:160])
    dotted = c.post("/jurisdiction/packs", json={
        **PACK, "requirements": [{**PACK["requirements"][0], "require": "Pset_WallCommon.FireRating"}]})
    check("a dot-form property path is a 422 — it parses and never matches",
          dotted.status_code == 422 and "TWO colons" in dotted.text, dotted.text[:160])

    imp = c.post("/jurisdiction/packs", json=PACK)
    check("a cited pack imports", imp.status_code == 201, imp.text[:200])
    check("  and appears in the library",
          len(c.get("/jurisdiction/packs?jurisdiction=TX").json()["packs"]) == 1)

    # --- the resolution that is the point of the feature ---------------------------------------
    pid = c.post("/projects", json={"name": "No Place"}).json()["id"]
    none = c.get(f"/projects/{pid}/jurisdiction/requirements").json()
    check("a project with NO jurisdiction adopts nothing",
          none["packs"] == [] and none["adopted"] is False)
    check("  and says why rather than defaulting", "belong to a jurisdiction" in none["why"])
    chk = c.get(f"/projects/{pid}/jurisdiction/check").json()
    check("  its check scores nothing and says so", chk["model_scored"] is False)

    tx = c.post("/projects", json={"name": "Texas Tower", "jurisdiction": "TX"}).json()
    tid = tx["id"]
    if tx.get("jurisdiction") != "TX":                       # set it explicitly if create ignored it
        c.patch(f"/projects/{tid}", json={"jurisdiction": "TX"})
    req = c.get(f"/projects/{tid}/jurisdiction/requirements").json()
    check("a TX project resolves the TX pack",
          [p["id"] for p in req["packs"]] == ["tx-example-city"], req)
    check("  reported as adopted", req["adopted"] is True)

    # --- the check, with attribution --------------------------------------------------------------
    model_index.load(tid, {"schema": "IFC4", "elements": ELEMENTS,
                           "counts": {"elements": len(ELEMENTS)}})
    r = c.get(f"/projects/{tid}/jurisdiction/check")
    check("GET /jurisdiction/check answers 200", r.status_code == 200, r.text[:200])
    J = r.json()
    check("  the model is scored", J["model_scored"] is True)
    check("  the unrated wall fails the requirement",
          J["failing_requirements"] == 1 and J["total_violations"] == 1, J)
    check("  and it is named", J["packs"][0]["rules"][0]["fail_guids"] == ["w2"])
    check("  the result carries WHOSE requirement it is",
          J["attribution"][0]["authority"] == PACK["authority"]
          and J["attribution"][0]["edition"] == "2026", J["attribution"])
    check("  and that it was not the example pack", J["attribution"][0]["is_example"] is False)
    check("  satisfied is False while anything fails", J["satisfied"] is False)

    model_index.load(tid, {"schema": "IFC4", "elements": [ELEMENTS[0]], "counts": {"elements": 1}})
    ok = c.get(f"/projects/{tid}/jurisdiction/check").json()
    check("a conforming model satisfies the pack", ok["satisfied"] is True, ok)

    # --- explicit application, and the 404s -------------------------------------------------------
    ex = c.get(f"/projects/{pid}/jurisdiction/check?pack=example").json()
    check("a pack can be applied explicitly to a project with no jurisdiction",
          [p["id"] for p in ex.get("packs", [])] == ["example"] or ex.get("model_scored") is False,
          ex)
    check("an unknown pack id is a 404",
          c.get(f"/projects/{tid}/jurisdiction/check?pack=nope").status_code == 404)
    check("an unknown pack id on requirements is a 404",
          c.get(f"/projects/{tid}/jurisdiction/requirements?pack=nope").status_code == 404)
    check("deleting the imported pack works",
          c.delete("/jurisdiction/packs/tx-example-city").status_code == 200)
    check("  deleting the built-in example is a 404",
          c.delete("/jurisdiction/packs/example").status_code == 404)

print()
if FAILED:
    print(f"jurisdiction_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("jurisdiction_route: all checks passed")
