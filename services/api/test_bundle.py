"""Portable project bundle round-trip. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bundle.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./bundle_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_bundle"
os.environ.pop("AEC_RBAC", None)
for f in ("./bundle_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

with TestClient(app) as c:
    tok = c.post("/auth/register", json={"username": "admin", "password": "supersecret"}).json()
    tok = c.post("/auth/login", json={"username": "admin", "password": "supersecret"}).json()["token"]

    # a project with real content across several tables
    pid = c.post("/projects", json={"name": "Bundle Source"}).json()["id"]
    rfi = c.post(f"/projects/{pid}/modules/rfi", headers=BEARER(tok),
                 json={"data": {"subject": "Beam clash", "question": "Reroute duct?"}}).json()
    sub = c.post(f"/projects/{pid}/modules/submittal", headers=BEARER(tok),
                 json={"data": {"title": "Rebar shop dwgs", "spec_section": "03 20 00"}}).json()
    # a BCF topic (pin) + a drawing markup
    top = c.post(f"/projects/{pid}/topics", headers=BEARER(tok),
                 json={"type": "rfi", "title": "Pin here", "anchor": {"x": 1, "y": 2, "z": 3}}).json()
    c.post(f"/projects/{pid}/topics/{top['id']}/comments", headers=BEARER(tok),
           json={"text": "look at this"})
    mk = c.post(f"/projects/{pid}/drawings/markup", headers=BEARER(tok),
                json={"sheet_id": "S-101", "x": 0.25, "y": 0.5, "note": "cloud here"})
    assert mk.status_code == 201, (mk.status_code, mk.text)

    # export the bundle
    r = c.get(f"/projects/{pid}/bundle", headers=BEARER(tok))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip", r.status_code
    blob = r.content
    import io, zipfile, json
    z = zipfile.ZipFile(io.BytesIO(blob))
    man = json.loads(z.read("manifest.json"))
    assert man["format"] == "aec.mmproj", man
    assert man["tables"].get("mod_rfi") == 1 and man["tables"].get("mod_submittal") == 1, man["tables"]
    assert man["tables"].get("topics") == 1 and man["tables"].get("drawing_markups") == 1, man["tables"]
    assert man["tables"].get("comments") == 1, man["tables"]   # topic child, scoped via topic_id

    # import it as a brand-new project (into the SAME db -> proves id regeneration / no PK clash)
    r2 = c.post("/projects/import-bundle", headers=BEARER(tok),
                files={"file": ("Bundle Source.mmproj", blob, "application/zip")},
                data={"name": "Bundle Restored"})
    assert r2.status_code == 201, (r2.status_code, r2.text)
    npid = r2.json()["id"]
    assert npid != pid and r2.json()["name"] == "Bundle Restored"

    # data restored, scoped to the new project
    rfis = c.get(f"/projects/{npid}/modules/rfi").json()
    assert len(rfis) == 1 and rfis[0]["data"]["subject"] == "Beam clash", rfis
    assert rfis[0]["id"] != rfi["id"], "record id should be regenerated on import"
    subs = c.get(f"/projects/{npid}/modules/submittal").json()
    assert len(subs) == 1 and subs[0]["data"]["spec_section"] == "03 20 00", subs
    tops = c.get(f"/projects/{npid}/topics", headers=BEARER(tok)).json()
    assert len(tops) == 1 and tops[0]["title"] == "Pin here", tops
    ntop = tops[0]["id"]
    # the comment's topic_id was remapped to the new topic
    cmts = c.get(f"/projects/{npid}/topics/{ntop}/comments", headers=BEARER(tok)).json()
    assert len(cmts) == 1 and cmts[0]["text"] == "look at this", cmts
    mks = c.get(f"/projects/{npid}/drawings/markup", headers=BEARER(tok)).json()
    assert len(mks) == 1 and mks[0]["sheet_id"] == "S-101", mks

    # the original project is untouched (still exactly one of each)
    assert len(c.get(f"/projects/{pid}/modules/rfi").json()) == 1
    assert len(c.get(f"/projects/{pid}/topics", headers=BEARER(tok)).json()) == 1

    # delete the restored project — rows + geometry gone, original still intact
    d = c.delete(f"/projects/{npid}", headers=BEARER(tok))
    assert d.status_code == 200 and d.json()["deleted"] is True, (d.status_code, d.text)
    assert d.json()["rows"].get("mod_rfi") == 1, d.json()["rows"]        # reports what it removed
    assert c.get(f"/projects/{npid}").status_code == 404
    assert npid not in {p["id"] for p in c.get("/projects").json()}
    assert len(c.get(f"/projects/{pid}/modules/rfi").json()) == 1         # source untouched
    assert c.delete("/projects/does-not-exist", headers=BEARER(tok)).status_code == 404

    # garbage upload is rejected cleanly
    bad = c.post("/projects/import-bundle", headers=BEARER(tok),
                 files={"file": ("x.mmproj", b"not a zip", "application/zip")})
    assert bad.status_code == 400, bad.status_code

    print("BUNDLE OK - export (geometry+data+blobs manifest), import as new project "
          "(id regen, topic/record FK remap, comment+markup restored), original untouched, "
          "delete-project (rows+geometry gone, 404 after), bad-file 400")
