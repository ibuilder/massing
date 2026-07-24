"""BCF-API-SRV 3.0 — version negotiation, the 3.0 topic shape (server_assigned_id + authorization
+ document_references), and attachments over the API (documents).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_bcf3.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bcf3.db"
os.environ["STORAGE_DIR"] = "./test_storage_bcf3"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_bcf3.db"):
    os.remove("./test_bcf3.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    # --- version negotiation advertises BOTH versions (a 2.1 manager keeps working) ----------------
    vers = c.get("/bcf/versions").json()["versions"]
    ids = {v["version_id"] for v in vers}
    assert ids == {"2.1", "3.0"}, ids
    assert c.get("/bcf/3.0/auth").json()["oauth2_token_url"] == "/auth/login"

    pid = c.post("/projects", json={"name": "Coordination"}).json()["id"]
    projects = c.get("/bcf/3.0/projects").json()
    mine = next(p for p in projects if p["project_id"] == pid)
    assert "createTopic" in mine["authorization"]["project_actions"], mine

    # --- create through 3.0 and read the 3.0 shape back -------------------------------------------
    r = c.post(f"/bcf/3.0/projects/{pid}/topics",
               json={"title": "Duct clashes beam", "topic_type": "Clash",
                     "topic_status": "Open", "priority": "High", "assigned_to": "mech@acme"})
    assert r.status_code == 201, r.text
    t = r.json()
    guid = t["guid"]
    assert t["server_assigned_id"] and t["server_assigned_id"] != guid       # our own stable handle
    assert t["topic_type"] == "Clash" and t["topic_status"] == "Open"
    assert t["document_references"] == [] and t["reference_links"] == []
    assert "update" in t["authorization"]["topic_actions"], t["authorization"]
    assert "Open" in t["authorization"]["topic_status"]

    got = c.get(f"/bcf/3.0/projects/{pid}/topics/{guid}").json()
    assert got["server_assigned_id"] == t["server_assigned_id"]
    assert any(x["guid"] == guid for x in c.get(f"/bcf/3.0/projects/{pid}/topics").json())
    assert c.get(f"/bcf/3.0/projects/{pid}/topics/no-such-guid").status_code == 404

    # comments + viewpoints round-trip on the 3.0 paths
    assert c.post(f"/bcf/3.0/projects/{pid}/topics/{guid}/comments",
                  json={"comment": "Re-route above the beam"}).status_code == 201
    comments = c.get(f"/bcf/3.0/projects/{pid}/topics/{guid}/comments").json()
    assert len(comments) == 1 and comments[0]["comment"] == "Re-route above the beam"
    assert c.get(f"/bcf/3.0/projects/{pid}/topics/{guid}/viewpoints").json() == []

    # --- documents over the API (the 3.0 addition) -------------------------------------------------
    assert c.get(f"/bcf/3.0/projects/{pid}/documents").json() == []
    up = c.post(f"/bcf/3.0/projects/{pid}/topics/{guid}/document_references",
                files={"file": ("markup.pdf", io.BytesIO(b"%PDF-1.4 clash markup"), "application/pdf")})
    assert up.status_code == 201, up.text
    doc_guid = up.json()["document_guid"]
    refs = c.get(f"/bcf/3.0/projects/{pid}/topics/{guid}/document_references").json()
    assert len(refs) == 1 and refs[0]["description"] == "markup.pdf"
    docs = c.get(f"/bcf/3.0/projects/{pid}/documents").json()
    assert len(docs) == 1 and docs[0]["guid"] == doc_guid and docs[0]["size"] == 21, docs
    dl = c.get(f"/bcf/3.0/projects/{pid}/documents/{doc_guid}")
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF"), dl.status_code
    # the topic now advertises its document, and a foreign project can't reach the bytes
    assert c.get(f"/bcf/3.0/projects/{pid}/topics/{guid}").json()["document_references"] == [doc_guid]
    other = c.post("/projects", json={"name": "Other"}).json()["id"]
    assert c.get(f"/bcf/3.0/projects/{other}/documents/{doc_guid}").status_code == 404
    assert c.get(f"/bcf/3.0/projects/{other}/documents").json() == []

    # --- the 2.1 surface is untouched by all of this -----------------------------------------------
    legacy = c.get(f"/bcf/2.1/projects/{pid}/topics").json()
    assert any(x["guid"] == guid for x in legacy)
    assert "server_assigned_id" not in legacy[0]                  # 2.1 stays 2.1

print("BCF3 OK - /bcf/versions advertises 2.1 AND 3.0; the 3.0 surface creates and serves topics in "
      "the newer shape (server_assigned_id distinct from the BCF guid, role-derived authorization "
      "actions, reference_links/document_references) with comments and viewpoints on the 3.0 paths; "
      "documents ride the API end to end (upload a PDF to a topic's document_references, list it "
      "project-wide, download the real bytes) and are project-scoped so another project 404s; the "
      "2.1 surface still answers exactly as before.")
