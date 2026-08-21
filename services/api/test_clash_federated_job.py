"""R24-RUNS-INBOX — the federated clash becomes a durable Run, and the actor stops being a claim.

The inbox (`apps/web/src/ui/runsInbox.ts`) has worked for weeks and is empty on most projects, because
the analyses it lists still run inside a request behind a modal. `clash_detect` was already a job kind
— but it is the SINGLE-MODEL narrow phase. The run the coordination screen performs is the
**federated** one, and it had no kind at all. This is that kind.

THE SECURITY HALF, AND WHY IT HAD TO LAND IN THE SAME CHANGE
------------------------------------------------------------
A job handler is called `fn(db, params)`. It never sees the Job row, so anything it needs to know
about *who* asked has to travel in `params` — and `params` is built in `routers/jobs.py` from the
caller's request body:

    jobs.enqueue(db, kind, pid, {**(params or {}), "project_id": pid}, actor=actor)

Every key the caller sent was merged straight through. That was harmless for exactly as long as no
handler read an identity out of it, which was true until now: `clash_intel.coordinate` takes an
`actor` and their party role and records both against every coordination issue it creates, reopens
and resolves. The moment this kind exists, `params["actor"]` is an identity claim — and a caller
could have supplied it.

So the route now writes `project_id` and `actor` **after** the caller's params, and the test below
enqueues with `params={"actor": "someone-else"}` and asserts the stored job carries the authenticated
user instead. This is not a vulnerability that shipped; it is one that would have, in the commit that
first read the field. *A latent hole becomes a live one the moment something reads it, and the read
and the fix belong in one change.*

THE REFUSAL
-----------
Fewer than two accessible discipline models raises, so the job lands in `error` with the sentence.
Returning an empty result instead would report "no clashes" for a run that compared nothing — and
"clean" and "there was nothing to compare" are the two answers a coordination report must never
merge. Asserted by running a real worker and reading the row, not by calling the handler directly.

...AND ITS TWIN, WHICH IS THE HALF THAT WAS MISSING
---------------------------------------------------
The first version of this file asserted only the refusal, and a suite that asserts only what must NOT
happen passes on a handler that does nothing at all: deleting the whole body of `_clash_federated`
and leaving the `raise` would have been green. So the second half registers two discipline models and
asserts the job SUCCEEDS, over both disciplines, finding cross-model clashes and grouping them into
tracked issues. Measured on the fixture: 64 clashes into 12 coordination issues.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_clash_federated_job.py
"""
from __future__ import annotations

import os
import pathlib
import re

os.environ["DATABASE_URL"] = "sqlite:///./test_clash_federated_job.db"
os.environ["STORAGE_DIR"] = "./test_storage_clash_federated_job"
os.environ["IFC_DIR"] = "./test_ifc_clash_federated_job"      # matches .gitignore test_ifc*/
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_clash_federated_job.db"):
    os.remove("./test_clash_federated_job.db")

import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import jobs  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Job  # noqa: E402
from aec_api.rbac import ROLE_ORDER  # noqa: E402
from aec_api.routers.jobs import _KIND_MIN_ROLE  # noqa: E402
from aec_data import massing  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# --- registration -------------------------------------------------------------------------------
check("clash_federated is a registered job kind", "clash_federated" in jobs.KINDS,
      ", ".join(sorted(jobs.KINDS)))
check("...and is MUTATING, so it takes the project lock -- coordinate() writes records",
      "clash_federated" in jobs._MUTATING_KINDS, ", ".join(sorted(jobs._MUTATING_KINDS)))
# The twin: a read-only kind must NOT be in the set, or the assertion above passes on a set
# containing everything.
check("...while the read-only kinds are still not mutating",
      not ({"ids_validate", "labor_estimate", "energy_analyze", "model_export", "cobie_export"}
           & jobs._MUTATING_KINDS),
      ", ".join(sorted(jobs._MUTATING_KINDS)))

# --- the queue must not be a SIDE DOOR around the stricter endpoint ------------------------------
# `_KIND_MIN_ROLE` exists in routers/jobs.py because a kind that does more than read needs a higher
# role than the generic `editor` on the enqueue route -- otherwise queueing a job is a way around the
# gate on the endpoint that does the same work. So the two must be compared, not assumed equal:
# whatever `POST /projects/{pid}/clash/federated` demands, enqueuing `clash_federated` must demand at
# least as much. They are both `editor` today, which is exactly why this is worth pinning -- an
# equality nobody wrote down is an equality nobody will notice breaking.
_analysis = (pathlib.Path(__file__).resolve().parents[0] / "src" / "aec_api" / "routers"
             / "analysis.py").read_text(encoding="utf-8")
_at = _analysis.index('@router.post("/projects/{pid}/clash/federated")')
_sig = _analysis[_at:_at + 1200]
_route_role = re.search(r'require_role\("(\w+)"\)', _sig)
_enqueue_role = _KIND_MIN_ROLE.get("clash_federated", "editor")
check("the sync federated-clash route's role is readable", _route_role is not None,
      _route_role.group(1) if _route_role else "not found in analysis.py")
if _route_role:
    check("enqueuing the job demands at least what the sync route demands -- the queue is not a "
          "side door", ROLE_ORDER[_enqueue_role] >= ROLE_ORDER[_route_role.group(1)],
          f"route={_route_role.group(1)} enqueue={_enqueue_role}")


with TestClient(app) as cl:
    pid = cl.post("/projects", json={"name": "Coord"}).json()["id"]

    # --- the actor is the AUTHENTICATED caller, not the body ------------------------------------
    r = cl.post(f"/projects/{pid}/jobs",
                json={"kind": "clash_federated",
                      "params": {"actor": "someone-else", "min_volume": 0.01}},
                headers={"X-User": "real.caller@example.test"})
    check("the enqueue is accepted", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
    job_id = r.json().get("id")

    with SessionLocal() as s:
        row = s.get(Job, job_id)
        stored = dict(row.params or {}) if row else {}
    check("params carry the AUTHENTICATED actor, not the one in the request body",
          stored.get("actor") == "real.caller@example.test",
          f"actor={stored.get('actor')!r}")
    check("...and the caller's other params still survive -- the route overrides two keys, not all",
          stored.get("min_volume") == 0.01, str(stored.get("min_volume")))
    check("...and project_id is server-set too", stored.get("project_id") == pid)

    # --- fewer than two models: the job FAILS, with the sentence ---------------------------------
    # A real worker, not a direct call: the thing under test is what a queued row becomes.
    jobs._run_one(SessionLocal)
    for _ in range(50):
        with SessionLocal() as s:
            row = s.get(Job, job_id)
            state, err = (row.state, row.error) if row else (None, None)
        if state in ("done", "error"):
            break
        time.sleep(0.1)
    check("a project with <2 discipline models FAILS the job rather than returning empty",
          state == "error", f"state={state}")
    check("...and the error names the remedy",
          bool(err) and "discipline models" in err,
          (err or "")[:120])


# ---------------------------------------------------------------------------------------------
# THE TWIN, and it is the half that was missing.
#
# Everything above proves the job REFUSES correctly. A suite that only asserts what must not happen
# passes on a handler that does nothing at all -- so this runs the same kind on a project that HAS
# two discipline models and asserts it produces a coordination result. Without it, deleting the
# entire body of `_clash_federated` and leaving the `raise` would have been green.
#
# Two copies of one small generated IFC, registered as STR and MEP: identical geometry in two models
# means guaranteed cross-model overlaps, and intra-model pairs are excluded by the engine, so a
# non-zero count is a real cross-discipline finding rather than a self-collision.
# ---------------------------------------------------------------------------------------------
_metrics = massing.compute_massing({"lot_width": 30, "lot_depth": 20, "far": 2.0,
                                    "floor_to_floor": 3.5, "height_limit": 14})
_ifc = Path(tempfile.gettempdir()) / "clash_fed_job_model.ifc"
massing.generate_ifc(_metrics, str(_ifc), name="Fed Job Test")
IFC_BYTES = _ifc.read_bytes()

with TestClient(app) as cl:
    pid2 = cl.post("/projects", json={"name": "Two models"}).json()["id"]
    for disc in ("STR", "MEP"):
        r = cl.post(f"/projects/{pid2}/models",
                    files={"file": (f"{disc}.ifc", IFC_BYTES, "application/octet-stream")},
                    data={"discipline": disc})
        assert r.status_code == 201, f"add {disc}: {r.status_code} {r.text[:160]}"

    jid = cl.post(f"/projects/{pid2}/jobs",
                  json={"kind": "clash_federated", "params": {"limit": 50}},
                  headers={"X-User": "coordinator@example.test"}).json()["id"]
    jobs._run_one(SessionLocal)
    state2 = err2 = None
    result = {}
    for _ in range(100):
        with SessionLocal() as s:
            row = s.get(Job, jid)
            if row:
                state2, err2, result = row.state, row.error, (row.result or {})
        if state2 in ("done", "error"):
            break
        time.sleep(0.1)

    check("with TWO discipline models the job SUCCEEDS", state2 == "done",
          f"state={state2} error={(err2 or '')[:160]}")
    check("...over both disciplines", set(result.get("disciplines") or []) == {"STR", "MEP"},
          str(result.get("disciplines")))
    check("...and finds cross-model clashes -- identical geometry in two models must collide",
          isinstance(result.get("count"), int) and result["count"] > 0, str(result.get("count")))
    coord = result.get("coordination") or {}
    check("...and the coordination layer ran, grouping them into tracked issues",
          isinstance(coord, dict) and isinstance(coord.get("group_count"), int)
          and coord["group_count"] > 0,
          f"group_count={coord.get('group_count')} new={coord.get('new')}")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("test_clash_federated_job OK")
