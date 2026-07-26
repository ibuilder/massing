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
                 json={"data": {"title": "Rebar shop dwgs", "spec_section": "03 20 00", "type": "Shop Drawing"}}).json()
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
    # R28-BUNDLE: the container is `.mass` v2 now. `.mmproj` was its name through v1.
    assert man["format"] == "massing.project" and man["version"] == 2, man
    assert man["extension"] == ".mass", man
    assert r.headers["content-disposition"].endswith('.mass"'), r.headers["content-disposition"]

    # THE CONTAINER EXPLAINS ITSELF. Documentation that lives in a repository is documentation the
    # person holding the file does not have — so a plain-English README travels inside the zip.
    readme = z.read("README.txt").decode("utf-8")
    for must in ("ZIP archive", "manifest.json", "data/<table>.json", "GlobalId", "geometry/"):
        assert must in readme, (must, readme[:400])

    # A FULL INVENTORY, so a reader can check what arrived against what was meant to be sent rather
    # than inferring completeness from the absence of an error.
    paths = {e["path"] for e in man["entries"]}
    assert "project.json" in paths and "README.txt" in paths, sorted(paths)[:10]
    assert all(isinstance(e["bytes"], int) for e in man["entries"]), man["entries"][:3]

    # WHAT DID NOT TRAVEL IS NAMED. A container that silently drops the account-specific tables looks
    # complete and is not.
    assert "users" in man["excluded"]["tables"] and "audit_log" in man["excluded"]["tables"], man["excluded"]
    assert "connections" in man["excluded"]["tables"], man["excluded"]
    assert man["excluded"]["why"], "an exclusion list with no reason is half a statement"
    assert any(".mmproj" in x for x in man["reads"]), man["reads"]
    assert man["tables"].get("mod_rfi") == 1 and man["tables"].get("mod_submittal") == 1, man["tables"]
    assert man["tables"].get("topics") == 1 and man["tables"].get("drawing_markups") == 1, man["tables"]
    assert man["tables"].get("comments") == 1, man["tables"]   # topic child, scoped via topic_id

    # import it as a brand-new project (into the SAME db -> proves id regeneration / no PK clash)
    r2 = c.post("/projects/import-bundle", headers=BEARER(tok),
                files={"file": ("Bundle Source.mass", blob, "application/zip")},
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
                 files={"file": ("x.mass", b"not a zip", "application/zip")})
    assert bad.status_code == 400, bad.status_code

    # --- a rename must not orphan a single saved file -------------------------------------------
    # v1 `.mmproj` containers still import. Renaming a format and abandoning everything anyone
    # already saved is not a rename, it is data loss.
    def _rewrap(src: bytes, **manifest_over) -> bytes:
        zin = zipfile.ZipFile(io.BytesIO(src))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
            for it in zin.infolist():
                if it.filename == "manifest.json":
                    m = json.loads(zin.read(it.filename)); m.update(manifest_over)
                    zo.writestr("manifest.json", json.dumps(m))
                else:
                    zo.writestr(it.filename, zin.read(it.filename))
        return out.getvalue()

    legacy = _rewrap(blob, format="aec.mmproj", version=1)
    rl = c.post("/projects/import-bundle", headers=BEARER(tok),
                files={"file": ("Old.mmproj", legacy, "application/zip")}, data={"name": "From v1"})
    assert rl.status_code == 201, (rl.status_code, rl.text)
    assert len(c.get(f"/projects/{rl.json()['id']}/modules/rfi").json()) == 1, "v1 data restored"

    # --- a container from a NEWER build is refused, not half-read ---------------------------------
    # It may hold structures this build would silently misinterpret, and a partially-imported project
    # is worse than a declined one: the user believes they have their data.
    future = _rewrap(blob, version=99)
    rf = c.post("/projects/import-bundle", headers=BEARER(tok),
                files={"file": ("Future.mass", future, "application/zip")})
    assert rf.status_code == 400, rf.status_code
    assert "newer build" in rf.text, rf.text

    # an unknown format id is refused too, and names what it expected
    alien = _rewrap(blob, format="someone.else")
    ra = c.post("/projects/import-bundle", headers=BEARER(tok),
                files={"file": ("Alien.mass", alien, "application/zip")})
    assert ra.status_code == 400 and "massing.project" in ra.text, ra.text

    print("BUNDLE OK - the project container is now `.mass` (massing.project v2), renamed from "
          ".mmproj because that name read as Microsoft Project to anyone who had not seen it before, "
          "while this container has never held a byte of XML or any proprietary format - it is a zip "
          "of JSON plus IFC. THE CONTAINER EXPLAINS ITSELF: a plain-English README.txt travels inside "
          "the zip, because documentation that lives in a repository is documentation the person "
          "holding the file does not have; the manifest carries a full entry inventory so a reader "
          "can check what arrived instead of inferring completeness from the absence of an error; and "
          "it NAMES WHAT DID NOT TRAVEL (users, audit log, settings, connections - account- and "
          "machine-specific) with the reason, because a container that drops them silently looks "
          "complete and is not. A rename must not orphan a single saved file, so v1 .mmproj still "
          "imports; and a container written by a NEWER build is REFUSED rather than half-read, since "
          "a partially-imported project is worse than a declined one - the user believes they have "
          "their data. Plus: export (geometry+data+blobs), import as new project (id regen, "
          "topic/record FK remap, comment+markup restored), original untouched, delete-project, "
          "bad-file 400.")
