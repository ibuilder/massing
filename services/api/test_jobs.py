"""JOB-QUEUE: durable background jobs — enqueue/claim/run/result, error capture, unknown-kind 400,
crash recovery (orphaned running → re-queued), endpoints + project scoping, real cobie_export kind.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_jobs.py"""
import os
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./_jobs_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_jobs")
os.environ.setdefault("IFC_DIR", "./_ifc_jobs")   # writable; default /app/ifc is read-only in the CI container
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_jobs_test.db"):
    os.remove("./_jobs_test.db")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from aec_api import jobs  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.models import Job  # noqa: E402

init_db()


def _wait(job_id: str, timeout: float = 15.0) -> Job:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with SessionLocal() as db:
            j = db.get(Job, job_id)
            if j and j.state in ("done", "error"):
                db.expunge(j)
                return j
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


# --- unknown kind fails at SUBMIT, not silently ----------------------------------------------------
with SessionLocal() as db:
    try:
        jobs.enqueue(db, "nope", None, {})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass

# --- crash recovery: a job left 'running' by a dead process re-queues on worker start -------------
with SessionLocal() as db:
    orphan = Job(kind="echo", project_id=None, params={"n": 1}, state="running")
    db.add(orphan)
    db.commit()
    orphan_id = orphan.id

jobs.start_worker()                                  # recovers the orphan, then runs it
j = _wait(orphan_id)
assert j.state == "done" and j.result == {"echo": {"n": 1}}, (j.state, j.result)

# --- happy path + error capture --------------------------------------------------------------------
def _boom(db, params):
    raise RuntimeError("kaboom")

jobs.register_kind("boom", _boom)
with SessionLocal() as db:
    ok = jobs.enqueue(db, "echo", None, {"hello": "world"})
    bad = jobs.enqueue(db, "boom", None, {})
j1, j2 = _wait(ok.id), _wait(bad.id)
assert j1.state == "done" and j1.result == {"echo": {"hello": "world"}}
assert j1.started_at is not None and j1.finished_at is not None
assert j2.state == "error" and "kaboom" in (j2.error or ""), j2.error
assert j2.result is None

# --- endpoints: enqueue → poll → list; cross-project 404; real cobie_export on a real model --------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Jobs"}).json()["id"]
    other = c.post("/projects", json={"name": "Other"}).json()["id"]

    r = c.post(f"/projects/{pid}/jobs", json={"kind": "echo", "params": {"a": 1}})
    assert r.status_code == 201, r.text[:200]
    jid = r.json()["id"]
    assert c.post(f"/projects/{pid}/jobs", json={"kind": "nope"}).status_code == 400
    assert c.get(f"/projects/{other}/jobs/{jid}").status_code == 404, "cross-project job access"

    _wait(jid)
    got = c.get(f"/projects/{pid}/jobs/{jid}").json()
    assert got["state"] == "done" and got["result"]["echo"]["a"] == 1, got
    lst = c.get(f"/projects/{pid}/jobs").json()["jobs"]
    assert any(x["id"] == jid for x in lst)

    # the real heavy kind: full-model COBie export in the background
    import tempfile

    from aec_data import massing  # noqa: E402
    metrics = massing.compute_massing({"lot_width": 14, "lot_depth": 10, "far": 1.5, "floor_to_floor": 3.5})
    ifc = Path(tempfile.gettempdir()) / "jobs_model.ifc"
    massing.generate_ifc(metrics, str(ifc), name="JobsModel")
    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("m.ifc", ifc.read_bytes(), "application/octet-stream")})
    assert up.status_code == 200, up.text[:160]
    r2 = c.post(f"/projects/{pid}/jobs", json={"kind": "cobie_export"})
    cj = _wait(r2.json()["id"], timeout=60)
    assert cj.state == "done" and cj.result["total_rows"] > 0, (cj.state, cj.error, cj.result)
    assert cj.result["sheets"]["Floor"] >= 1, cj.result

    # JOB-QUEUE migration: the compiled drawing-set PDF as an ARTIFACT job — the PDF parks in object
    # storage and /jobs/{id}/artifact streams it back (409 while running, 404 without an artifact)
    r3 = c.post(f"/projects/{pid}/jobs", json={"kind": "compiled_set_pdf", "params": {"max_sheets": 4}})
    pj_id = r3.json()["id"]
    pj = _wait(pj_id, timeout=120)
    assert pj.state == "done" and pj.result["artifact_key"].endswith(".pdf"), (pj.state, pj.error)
    assert pj.result["bytes"] > 1000, pj.result
    art = c.get(f"/projects/{pid}/jobs/{pj_id}/artifact")
    assert art.status_code == 200 and art.content[:4] == b"%PDF", art.status_code
    assert "application/pdf" in art.headers["content-type"], art.headers
    # a result-only job (echo) has no artifact → 404
    assert c.get(f"/projects/{pid}/jobs/{jid}/artifact").status_code == 404

    # JOB-QUEUE: heavy geometry exports as artifact jobs — .glb tessellated off-thread, parked in
    # storage, streamed back as a valid binary glTF; a bad format fails on the row (worker survives)
    r4 = c.post(f"/projects/{pid}/jobs", json={"kind": "model_export", "params": {"format": "glb"}})
    gj = _wait(r4.json()["id"], timeout=120)
    assert gj.state == "done" and gj.result["artifact_key"].endswith(".glb"), (gj.state, gj.error)
    ga = c.get(f"/projects/{pid}/jobs/{r4.json()['id']}/artifact")
    assert ga.status_code == 200 and ga.content[:4] == b"glTF", ga.content[:8]
    assert "model/gltf-binary" in ga.headers["content-type"], ga.headers
    r5 = c.post(f"/projects/{pid}/jobs", json={"kind": "model_export", "params": {"format": "step"}})
    bj = _wait(r5.json()["id"], timeout=60)
    assert bj.state == "error" and "unknown export format" in (bj.error or ""), (bj.state, bj.error)

    # PERF-3 (CLASH-JOBS): the narrow-phase clash runs on the worker (off the request slot) and
    # returns its summary as a result (not an artifact)
    r6 = c.post(f"/projects/{pid}/jobs",
                json={"kind": "clash_detect",
                      "params": {"a": "IfcWall", "b": "IfcSlab", "narrow": False}})
    cj2 = _wait(r6.json()["id"], timeout=120)
    assert cj2.state == "done" and "count" in cj2.result and "clashes" in cj2.result, (cj2.state, cj2.error)

jobs.stop_worker()
print("JOB-QUEUE OK - unknown kind 400s at submit; orphaned running job re-queued on worker start and "
      "completed (crash recovery); echo round-trips with timestamps; handler exception captured on the "
      "row (worker survives); endpoints enqueue/poll/list with cross-project 404; the real cobie_export "
      "kind parses the model in the background and reports per-sheet counts; model_export tessellates "
      "the .glb off-thread into a streamed artifact (valid glTF magic) and a bad format errors on the "
      "row; clash_detect runs the narrow-phase clash on the worker and returns its summary.")
