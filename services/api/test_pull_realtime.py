"""Real-time collaborative pull board (M3): the board change-signature that drives the SSE live-refresh,
and the optimistic lock that stops one trade silently overwriting another's edit.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_pull_realtime.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_pull_realtime.db"
os.environ["STORAGE_DIR"] = "./test_storage_pull_realtime"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_pull_realtime.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient            # noqa: E402
from aec_api.main import app                         # noqa: E402


def _mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Pull Board Live"}).json()["id"]

    # empty board -> signature count 0
    sig0 = c.get(f"/projects/{pid}/pull-plan/board").json()  # board itself works
    assert sig0["total"] == 0, sig0["total"]

    # add two sticky notes; the board signature must move (count + latest modified_at)
    t1 = _mk(c, pid, "pull_plan_task", {"task": "Form + pour footings", "trade": "Concrete", "planned_week": "W1"})
    _mk(c, pid, "pull_plan_task", {"task": "Set embeds", "trade": "Steel", "planned_week": "W1"})
    rid = t1["id"]

    # the board change-signature (drives the SSE stream) reflects the two notes + a latest timestamp
    from aec_api import pull_plan                     # noqa: E402
    from aec_api.db import SessionLocal               # noqa: E402
    with SessionLocal() as db:
        sig = pull_plan.signature(db, pid)
    assert sig["count"] == 2 and sig["latest"], sig

    # the record carries a modified_at the client can lock against
    rec = c.get(f"/projects/{pid}/modules/pull_plan_task/{rid}").json()
    stamp = rec["modified_at"]
    assert stamp, "record must expose modified_at for the optimistic lock"

    # --- optimistic lock ---
    # a write carrying the current modified_at succeeds (no concurrent change)
    ok = c.patch(f"/projects/{pid}/modules/pull_plan_task/{rid}?expected_modified_at={stamp}",
                 json={"trade": "Concrete", "planned_week": "W2"})
    assert ok.status_code == 200, ok.text[:200]

    # a second write still carrying the *stale* stamp is rejected 409 (someone else moved it first)
    conflict = c.patch(f"/projects/{pid}/modules/pull_plan_task/{rid}?expected_modified_at={stamp}",
                       json={"planned_week": "W3"})
    assert conflict.status_code == 409, f"expected 409, got {conflict.status_code}: {conflict.text[:160]}"
    detail = conflict.json()["detail"]
    assert detail["error"] == "stale_write" and detail["modified_at"], detail

    # a write with no lock still goes through (backward-compatible: the check is opt-in)
    unlocked = c.patch(f"/projects/{pid}/modules/pull_plan_task/{rid}", json={"planned_week": "W4"})
    assert unlocked.status_code == 200, unlocked.text[:200]

    # a write carrying the now-current stamp succeeds again (reconcile-then-retry path)
    fresh = c.get(f"/projects/{pid}/modules/pull_plan_task/{rid}").json()["modified_at"]
    retry = c.patch(f"/projects/{pid}/modules/pull_plan_task/{rid}?expected_modified_at={fresh}",
                    json={"trade": "Concrete"})
    assert retry.status_code == 200, retry.text[:200]

print("PULL-REALTIME OK - board signature moves on edit (drives the SSE live-refresh); optimistic lock "
      "rejects a stale write with 409 (+ current modified_at) while an un-locked write stays "
      "backward-compatible and a reconciled retry succeeds")
