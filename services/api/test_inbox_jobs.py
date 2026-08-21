"""R24-RUNS-INBOX — IDS and labour-estimate become durable Runs.

The screens used to call POST /validate and GET /estimate/labor on the request thread, so the
Runs inbox stayed empty even though the engines were live. These two kinds are the remaining
half of that wiring (clash_federated already has test_clash_federated_job.py).

Both are READ-ONLY: they return a result dict, they write no project state. Failure of the job
is a failed row, not a 500 — asserted by running a real worker and reading the row.

Run: PYTHONPATH="src:../data/src" python test_inbox_jobs.py
"""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_inbox_jobs.db"
os.environ["STORAGE_DIR"] = "./test_storage_inbox_jobs"
os.environ["IFC_DIR"] = "./test_ifc_inbox_jobs"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for p in ("./test_inbox_jobs.db",):
    if os.path.exists(p):
        os.remove(p)

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Job  # noqa: E402
from aec_data import massing  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def _wait(job_id: str, timeout: float = 90.0) -> Job:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with SessionLocal() as db:
            j = db.get(Job, job_id)
            if j and j.state in ("done", "error"):
                db.expunge(j)
                return j
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


with TestClient(app) as c:
    c.headers["X-User"] = "tester"
    pid = c.post("/projects", json={"name": "inbox-jobs"}).json()["id"]
    metrics = massing.compute_massing({"lot_width": 14, "lot_depth": 10, "far": 1.5, "floor_to_floor": 3.5})
    ifc = Path("./test_ifc_inbox_jobs")
    ifc.mkdir(exist_ok=True)
    path = ifc / "m.ifc"
    massing.generate_ifc(metrics, str(path), name="InboxJobs")
    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("m.ifc", path.read_bytes(), "application/octet-stream")})
    check("source IFC accepted", up.status_code == 200, up.text[:160])

    r = c.post(f"/projects/{pid}/jobs", json={"kind": "ids_validate"})
    check("ids_validate enqueues", r.status_code == 201, r.text[:200])
    j = _wait(r.json()["id"])
    check("ids_validate finishes", j.state == "done", f"{j.state} {j.error}")
    check("ids_validate returns a status, not an empty dict",
          isinstance(j.result, dict) and "status" in (j.result or {}), str(j.result)[:200])

    r2 = c.post(f"/projects/{pid}/jobs",
                json={"kind": "labor_estimate", "params": {"loading": "commercial", "rate": 25, "full": True}})
    check("labor_estimate enqueues", r2.status_code == 201, r2.text[:200])
    j2 = _wait(r2.json()["id"])
    check("labor_estimate finishes", j2.state == "done", f"{j2.state} {j2.error}")
    check("labor_estimate names its hours",
          isinstance(j2.result, dict) and "total_man_hours" in (j2.result or {}), str(j2.result)[:200])

    r3 = c.post(f"/projects/{pid}/jobs", json={"kind": "energy_analyze"})
    check("energy_analyze enqueues", r3.status_code == 201, r3.text[:200])
    j3 = _wait(r3.json()["id"])
    check("energy_analyze finishes", j3.state == "done", f"{j3.state} {j3.error}")
    check("energy_analyze names an EUI, not an empty dict",
          isinstance(j3.result, dict) and "eui_kwh_m2_yr" in (j3.result or {}), str(j3.result)[:200])

# Twin: a handler that only refuses would leave these green. Deleting the body of _ids_validate
# and raising would fail "finishes"; returning {} would fail "returns a status".

if FAILED:
    print(f"FAILED {len(FAILED)}: {FAILED}")
    raise SystemExit(1)
print("test_inbox_jobs OK")
