"""AGENT-TRAIL — `GET /agent-packs/runs`, the estate-wide agent governance console.

Two claims are asserted here, and the second is the one that matters.

**It answers across projects.** The per-project console answers "what ran here", which is the wrong
altitude for the question an enterprise asks before granting an agent access and after an incident:
*whose agent ran what, anywhere.* A reviewer who must open twenty consoles and add them up is not
being governed by one.

**IT IS ADMIN-ONLY, AND THAT FOLLOWS FROM AN EXISTING FACT RATHER THAN FROM TASTE.** These rows come
out of `audit_log`, and `GET /audit` is already admin-only. So a non-admin estate-wide view here
would be a way to read audit rows without being an admin — a privilege-escalation surface wearing
the name of a governance feature. Asserted with a real non-admin session rather than by reading the
dependency's name, because `Depends(current_user)` *identifies* and reads exactly like a gate; the
repository's own SEC-GLOBAL-AUTHZ note records that being how such a hole survives review.

Run: PYTHONPATH=src:../data/src ./.venv/bin/python test_agent_runs_route.py
"""
from __future__ import annotations

import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_agent_runs_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_agent_runs_route"
os.environ["AEC_RBAC"] = "1"
os.environ.pop("AEC_TRUST_XUSER", None)
os.environ.pop("AEC_ADMIN_EMAILS", None)
for _f in ("./test_agent_runs_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import AuditLog  # noqa: E402

Base.metadata.create_all(bind=engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    """Record one assertion, printing the measured value beside a failure.

    `detail` carries what was actually seen, not a restatement of the expectation — a failure that
    prints only its own name tells the next reader nothing they did not already have.
    """
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


c = TestClient(app)

# The first registration on an empty user table bootstraps the platform admin (AEC_ADMIN_EMAILS is
# unset here, which is the single-operator case R43-ORG-OWNERSHIP leaves granting "admin").
def _login(username: str, password: str) -> str:
    """A bearer token for `username`. Registration returns the account, not a session."""
    r = c.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text[:200]
    return r.json()["token"]


r = c.post("/auth/register", json={"username": "boss@x.test", "password": "correct-horse-1"})
assert r.status_code in (200, 201), r.text[:200]
assert r.json()["role"] == "admin", r.json()
admin_tok = _login("boss@x.test", "correct-horse-1")
r = c.post("/auth/register", json={"username": "worker@x.test", "password": "correct-horse-2"},
           headers={"Authorization": f"Bearer {admin_tok}"})
assert r.status_code in (200, 201), r.text[:200]
# The worker must NOT be an admin, or the refusal below would pass for the wrong reason — the
# whole assertion is that a signed-in non-admin is turned away.
assert r.json().get("role") != "admin", r.json()
worker_tok = _login("worker@x.test", "correct-horse-2")
AH = {"Authorization": f"Bearer {admin_tok}"}
WH = {"Authorization": f"Bearer {worker_tok}"}

t0 = datetime.now(timezone.utc)
with SessionLocal() as db:
    db.add(AuditLog(ts=t0 - timedelta(hours=2), actor="alice", action="mcp.run", method="MCP",
                    detail={"tool": "standards_check", "pack": "Submittal Review", "ok": True,
                            "project_id": "P-ONE"}))
    db.add(AuditLog(ts=t0 - timedelta(hours=1), actor="bob", action="mcp.run", method="MCP",
                    detail={"tool": "clash", "pack": "QA", "ok": False, "project_id": "P-TWO"}))
    db.commit()

# --- the gate, asserted against a live non-admin session -----------------------------------------
r = c.get("/agent-packs/runs", headers=WH)
check("A NON-ADMIN IS REFUSED — these are audit rows, and /audit is admin-only",
      r.status_code in (401, 403), r.status_code)
r = c.get("/agent-packs/runs")
check("  and so is an anonymous caller", r.status_code in (401, 403), r.status_code)

# --- what an admin actually gets ------------------------------------------------------------------
r = c.get("/agent-packs/runs", headers=AH)
check("an admin gets the console", r.status_code == 200, r.status_code)
body = r.json()
check("  spanning projects a per-project view would separate",
      {x["project_id"] for x in body["runs"]} >= {"P-ONE", "P-TWO"},
      sorted({x["project_id"] for x in body["runs"] if x["project_id"]}))
check("  counting runs per ACTOR — the estate-wide question a tool tally cannot answer",
      body["by_actor"].get("alice") == 1 and body["by_actor"].get("bob") == 1, body["by_actor"])
check("  carrying the pack each run came through", {x["pack"] for x in body["runs"]}
      >= {"Submittal Review", "QA"}, [x["pack"] for x in body["runs"]])
check("  and the failure, because 'what did it try' is the post-incident question",
      body["failure_count"] == 1, body["failure_count"])
check("  the catalog rides along, so the console can say what each pack is",
      body["pack_count"] >= 1 and isinstance(body["packs"], list), body.get("pack_count"))
check("  a full window is not reported as truncated",
      body["truncated"] is False and body["run_total"] == body["run_count"],
      (body["run_total"], body["run_count"]))

# The window is clamped, not trusted -- and a clamped window still tells the truth about the total.
one = c.get("/agent-packs/runs?limit=1", headers=AH).json()
check("a narrowed window says so rather than reporting its slice as the whole",
      one["run_count"] == 1 and one["run_total"] == 2 and one["truncated"] is True,
      (one["run_count"], one["run_total"], one["truncated"]))
check("  limit is clamped rather than trusted",
      c.get("/agent-packs/runs?limit=0", headers=AH).json()["run_count"] == 1)

print()
if FAILED:
    print(f"agent runs route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print('agent runs route OK - the estate-wide agent console spans projects and counts by actor, and '
      'it is admin-only because its rows are audit rows: asserted with a real non-admin session, '
      'not by reading the dependency\'s name')
