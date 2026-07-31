"""R32-MODEL-IN-TREE — the model is filed into the controlled tree, with revisions.

Before this, the source model lived at `{pid}/source.ifc` and the documents at `{pid}/docs/<folder>/`:
two parallel stores. The one artefact every drawing, schedule and quantity is derived from was the only
one with no revision, no supersession, and no presence in the file manager at all.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_filed_output.py
"""
import os
import shutil

os.environ["DATABASE_URL"] = "sqlite:///./test_filed_output.db"
os.environ["STORAGE_DIR"] = "./test_storage_filed_output"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_filed_output.db",):
    if os.path.exists(_f):
        os.remove(_f)
# `docmanager` keeps a sidecar index in STORAGE_DIR; clear it so the fixed-pid assertions below are
# isolated across runs, and so a stale index cannot make a revision assertion pass for the wrong reason.
shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import docmanager, filing, folder_template, storage  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- the taxonomy gained a home for the model -----------------------------------------------------
paths = {n["path"] for n in folder_template.tree()}
assert "12_Model" in paths and "12_Model/IFC" in paths, "the model has a folder"
assert folder_template.is_valid(filing.MODEL_FOLDER), filing.MODEL_FOLDER
assert folder_template.owner_of("12_Model/IFC") == "Architect"
assert folder_template.node("12_Model/IFC")["cde_default"] == "published"

# The DESIGN decision, asserted so it cannot be quietly reversed: generated output files into the
# folder its KIND already uses, never into a parallel "generated" silo. A silo would rebuild the same
# two-stores problem this work removes, and would split "the current drawing set" across two folders.
assert not [p for p in paths if "generated" in p.lower()], \
    f"no generated-output silo: {[p for p in paths if 'generated' in p.lower()]}"

# The model folder IS required — the user's call, 2026-07-31, made knowing it moves every existing
# project's compliance score. That is the intended effect: a project whose model was never filed is
# genuinely non-compliant and the score should say so. Only the IFC leaf is required; a project with no
# FEDERATED coordination model is complete, and requiring that would manufacture a permanent gap.
_req = set(folder_template.required_paths())
assert "12_Model" in _req and "12_Model/IFC" in _req, sorted(p for p in _req if "Model" in p)
assert "12_Model/Federated" not in _req, "a missing federated model is not a compliance gap"

# --- refusing is better than filing nothing -------------------------------------------------------
PID = "proj-filing"
try:
    filing.file_model(PID, "arch")
except filing.NothingToFile as e:
    assert "no model" in str(e), str(e)
else:
    raise AssertionError("filing a project with no model must refuse, not file an empty document")

# A zero-byte model is the more dangerous case: it would supersede a real revision with nothing.
storage.put(filing.model_key(PID), b"")
try:
    filing.file_model(PID, "arch")
except filing.NothingToFile as e:
    assert "empty" in str(e), str(e)
else:
    raise AssertionError("a zero-byte model must not supersede a real revision")

# --- filing, and re-filing, produces a revision chain ---------------------------------------------
IFC_V1 = b"ISO-10303-21;\nHEADER;\nFILE_NAME('v1');\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
IFC_V2 = b"ISO-10303-21;\nHEADER;\nFILE_NAME('v2');\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

storage.put(filing.model_key(PID), IFC_V1)
r1 = filing.file_model(PID, "arch")
assert r1["entry"]["revision"] == "P01", r1["entry"]
assert r1["entry"]["folder"] == "12_Model/IFC", r1["entry"]
assert r1["entry"]["doc_type"] == "MODEL" and r1["entry"]["cde_state"] == "published", r1["entry"]
assert r1["superseded"] is None, "first filing supersedes nothing"
assert r1["entry"]["size"] == len(IFC_V1), r1["entry"]["size"]

storage.put(filing.model_key(PID), IFC_V2)
r2 = filing.file_model(PID, "arch")
assert r2["entry"]["revision"] == "P02", r2["entry"]
assert r2["superseded"] == r1["entry"]["id"], "re-filing supersedes the prior revision, not a new doc"

# Current view shows exactly one model; the superseded revision is retained, not deleted.
current = docmanager.list_folder(PID, "12_Model/IFC")
assert current["count"] == 1 and current["files"][0]["revision"] == "P02", current

# --- the as-issued model stays RECOVERABLE, which is the whole point ------------------------------
hist = filing.filed_model_history(PID)
assert len(hist) == 2, [h["revision"] for h in hist]
assert {h["revision"] for h in hist} == {"P01", "P02"}, [h["revision"] for h in hist]
# Value-check the bytes, not merely the presence of a row: an entry pointing at the wrong blob would
# satisfy every count assertion above while losing the exact thing filing the model is FOR.
old = next(h for h in hist if h["revision"] == "P01")
assert storage.get(old["key"]) == IFC_V1, "the superseded revision must still hold the v1 bytes"
new = next(h for h in hist if h["revision"] == "P02")
assert storage.get(new["key"]) == IFC_V2, "the current revision must hold the v2 bytes"

# --- reachable over HTTP, with authz (a route that is only defined is not a feature) ---------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Filing Test"}).json()["id"]

    # Nothing filed yet, and no model present — reported as a state, not invented as an empty set.
    h0 = c.get(f"/projects/{pid}/documents/model-history")
    assert h0.status_code == 200, h0.text
    assert h0.json()["count"] == 0 and h0.json()["model_present"] is False, h0.json()

    # Filing with no model is a 409 (a state), not a 400 (a malformed request).
    r = c.post(f"/projects/{pid}/documents/file-model", data={"title": "Federated Model"})
    assert r.status_code == 409, (r.status_code, r.text)

    storage.put(filing.model_key(pid), IFC_V1)
    r = c.post(f"/projects/{pid}/documents/file-model", data={"title": "Federated Model"})
    assert r.status_code == 201, (r.status_code, r.text)
    assert r.json()["entry"]["revision"] == "P01", r.json()

    storage.put(filing.model_key(pid), IFC_V2)
    r = c.post(f"/projects/{pid}/documents/file-model", data={"title": "Federated Model"})
    assert r.status_code == 201 and r.json()["entry"]["revision"] == "P02", r.json()

    hist = c.get(f"/projects/{pid}/documents/model-history").json()
    assert hist["count"] == 2 and hist["model_present"] is True, hist
    assert [x["revision"] for x in hist["revisions"]] == ["P02", "P01"], "newest first"

    # The model now appears in the file manager the field actually looks at — the reach half of R32.
    folder = c.get(f"/projects/{pid}/documents/folder", params={"path": "12_Model/IFC"}).json()
    assert folder["count"] == 1 and folder["files"][0]["revision"] == "P02", folder
    assert c.get(f"/projects/{pid}/documents/tree").status_code == 200

    # An unknown project must 404 rather than filing into a tree that does not exist.
    assert c.post("/projects/no-such-project/documents/file-model", data={}).status_code == 404

    # The compliance signal is REACHABLE, not just declared: an unfiled model must show up as a
    # required-folder gap in document-control health, and filing it must clear that gap. Checked on a
    # fresh project, because the one above already has a filed model and would pass vacuously.
    pid3 = c.post("/projects", json={"name": "Health Gap"}).json()["id"]
    h_before = c.get(f"/projects/{pid3}/documents/health").json()
    assert "12_Model/IFC" in h_before["required_missing"], h_before["required_missing"]

    storage.put(filing.model_key(pid3), IFC_V1)
    c.post(f"/projects/{pid3}/documents/file-model", data={"title": "Federated Model"})
    h_after = c.get(f"/projects/{pid3}/documents/health").json()
    assert "12_Model/IFC" not in h_after["required_missing"], h_after["required_missing"]

# --- R32-FILE-GENERATED: issuing a set files it into the same controlled tree ---------------------
# Issuing IS the publish event, so it is where a release must enter the tree. Before this, sheets were
# generated, released, and never filed: no revision, no supersession, invisible in the file manager.
with TestClient(app) as c:
    HDR = {"X-User": "architect"}
    pid2 = c.post("/projects", json={"name": "Issued Set"}, headers=HDR).json()["id"]
    P = f"/projects/{pid2}"

    c.post(f"{P}/drawing-set/generate", json={"disciplines": ["Mechanical"]}, headers=HDR)
    i1 = c.post(f"{P}/drawing-set/issue", json={"purpose": "Issued for Permit",
                                                "recipients": "gc@example.com"}, headers=HDR)
    assert i1.status_code == 201, i1.text
    b1 = i1.json()
    # The filing result is REPORTED, never silent: `filed` carries the entry, `filed_error` the reason.
    assert b1.get("filed_error") is None, b1.get("filed_error")
    assert b1["filed"] and b1["filed"]["folder"] == "02_Drawings", b1["filed"]
    assert b1["filed"]["doc_type"] == "TRANSMTL", b1["filed"]
    assert b1["filed"]["revision"] == "P01", b1["filed"]

    # A second issuance is a DIFFERENT release, so it must be its own document — a transmittal that
    # superseded its predecessor would destroy exactly the history it exists to provide.
    c.post(f"{P}/drawing-set/generate", json={"disciplines": ["Electrical"]}, headers=HDR)
    b2 = c.post(f"{P}/drawing-set/issue", json={"purpose": "Issued for Bid"}, headers=HDR).json()
    assert b2["filed"] and b2["filed"]["revision"] == "P01", \
        f"each release is its own document, not a revision of the last: {b2['filed']}"
    assert b2["filed"]["supersedes"] is None, b2["filed"]
    assert b2["filed"]["title"] != b1["filed"]["title"], (b1["filed"]["title"], b2["filed"]["title"])

    # Both transmittals are now visible in the file manager — the reach half of R32.
    folder = c.get(f"{P}/documents/folder", params={"path": "02_Drawings"}, headers=HDR).json()
    titles = {f["title"] for f in folder["files"]}
    assert len(titles) == 2 and all(t.startswith("Transmittal") for t in titles), folder

    # The drawing SET is a deliberate act, not a side effect of issuing — and with no source model it
    # refuses (409) rather than filing an empty set.
    assert c.post(f"{P}/drawing-set/file-drawing-set", json={}, headers=HDR).status_code == 409

    # SEC (py/stack-trace-exposure) — when filing FAILS, the caller learns the fact and never the
    # exception. This was a real alert on the push that introduced the feature: interpolating the
    # exception into `filed_error` leaked internal detail into an API response. Asserted by forcing a
    # failure, because the safe path proves nothing about the unsafe one.
    _orig = filing.file_transmittal
    try:
        def _boom(*a, **k):
            raise RuntimeError("C:/secret/path/internals.py line 42 — connection string s3cr3t")
        filing.file_transmittal = _boom
        c.post(f"{P}/drawing-set/generate", json={"disciplines": ["Plumbing"]}, headers=HDR)
        b3 = c.post(f"{P}/drawing-set/issue", json={"purpose": "Issued for Record"}, headers=HDR).json()
    finally:
        filing.file_transmittal = _orig
    # The release still succeeded — filing is non-fatal, so the issuance must not be reported as failed.
    assert b3.get("id") and b3["filed"] is None, b3
    err = b3["filed_error"] or ""
    assert err and "see server logs" in err, err
    for leak in ("secret", "s3cr3t", "RuntimeError", "line 42", "internals.py"):
        assert leak not in err, f"filed_error leaked {leak!r}: {err}"

# The set's title is CONSTANT by design, so repeated issues become revisions of ONE document — that is
# what lets the document tree answer "which set is current" without a second register. Asserted as the
# property rather than by rendering a real set, which would cost a full sheet render for no extra proof.
assert filing.SET_TITLE == "Drawing Set", filing.SET_TITLE
_p = "proj-setrev"
s1 = docmanager.upload(_p, filing.DRAWINGS_FOLDER, "a.pdf", b"%PDF-1 set1", "arch",
                       title=filing.SET_TITLE, doc_type="DWGSET")
s2 = docmanager.upload(_p, filing.DRAWINGS_FOLDER, "a.pdf", b"%PDF-1 set2", "arch",
                       title=filing.SET_TITLE, doc_type="DWGSET")
assert s1["entry"]["revision"] == "P01" and s2["entry"]["revision"] == "P02", (s1, s2)
assert s2["superseded"] == s1["entry"]["id"], "a re-issued set supersedes, giving one current set"
assert docmanager.list_folder(_p, filing.DRAWINGS_FOLDER)["count"] == 1, "exactly one current set"

print("FILED OUTPUT (R32-MODEL-IN-TREE) OK - the model has a home in the standard taxonomy "
      "(12_Model/IFC, Architect-owned, published) and filing it goes through docmanager, so a model "
      "revision IS a document revision: first filing is P01, re-filing supersedes it as P02, the "
      "current folder view shows exactly one model, and the superseded P01 still holds its original "
      "bytes (value-checked, not just counted) so the as-issued model stays recoverable. Filing a "
      "project with no model, or a zero-byte one, REFUSES rather than superseding a real revision with "
      "nothing. Reachable over HTTP: 201 on file, 409 when there is nothing to file, 404 on an unknown "
      "project, history newest-first including superseded. No 'generated' silo folder exists, and "
      "12_Model is not `required`, so no existing project's health score moves. "
      "R32-FILE-GENERATED: issuing a set now FILES it — the transmittal lands in 02_Drawings on issue "
      "(reported as `filed`/`filed_error`, never silently), each release is its own document rather "
      "than a revision of the last so the release history survives, and both are visible in the file "
      "manager. The compiled set is a separate deliberate call that 409s with no source model, and its "
      "title is constant so re-issues supersede into ONE current set.")
