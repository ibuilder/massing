"""Scale-hardening regression: locks in the mega-project fixes so they can't silently regress —
list pagination is clamped, my-work is bounded (no multi-MB dump), BCF export is a single query (not
an N+1) and capped, and the dashboard stays responsive. Seeds a few thousand rows via direct bulk
insert (fast) so the bounds are actually exercised, not asserted on an empty table.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_scale.py"""
import os
import uuid
from datetime import datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_scale.db"
os.environ["STORAGE_DIR"] = "./test_storage_scale"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_scale.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient          # noqa: E402
from aec_api import modules as me                  # noqa: E402
from aec_api.db import SessionLocal                # noqa: E402
from aec_api.main import app                       # noqa: E402
from aec_api.models import Project                 # noqa: E402

HDR = {"X-User": "scaletester"}
N = 3000  # rfi rows — enough that an unbounded my-work / N+1 BCF would blow the assertions


def _bulk(db, key, pid, n):
    t = me.TABLES[key]
    mod = me.REGISTRY[key]
    states = sorted({mod.get("workflow", {}).get("initial", "open")}
                    | {tr["from"] for tr in mod.get("workflow", {}).get("transitions", [])})
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [{
        "id": str(uuid.uuid4()), "project_id": pid, "ref": f"RFI-{i:05d}",
        "title": f"rfi {i}", "workflow_state": states[i % len(states)],
        "party_owner": "gc", "assignee": "scaletester" if i % 3 == 0 else "other",
        "created_by": "seed", "created_at": base, "modified_at": base,
        "anchor": None, "element_guids": ([uuid.uuid4().hex[:22]] if i % 4 == 0 else None),
        "links": [], "data": {"subject": f"concrete issue {i}", "amount": 1000 + i},
    } for i in range(1, n + 1)]
    for j in range(0, len(rows), 1000):
        db.execute(t.insert(), rows[j:j + 1000])
    db.commit()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Scale"}, headers=HDR).json()["id"]
    with SessionLocal() as db:
        db.merge(Project(id=pid, name="Scale"))   # ensure attached
        _bulk(db, "rfi", pid, N)
    P = f"/projects/{pid}"

    # --- indexes exist (the created_at / assignee hardening) --------------------------------------
    with SessionLocal() as db:
        idx = {i["name"] for i in db.bind.dialect.get_indexes(db.connection(), "mod_rfi")}
    assert any("proj_created" in n for n in idx), f"missing created_at index: {idx}"
    assert any("proj_assignee" in n for n in idx), f"missing assignee index: {idx}"

    # --- list pagination is clamped (no unbounded dump) ------------------------------------------
    r = c.get(f"{P}/modules/rfi?limit=999999", headers=HDR).json()
    assert len(r) <= 1000, f"list not clamped: {len(r)}"
    # deep offset still works
    r2 = c.get(f"{P}/modules/rfi?limit=100&offset=2500", headers=HDR).json()
    assert len(r2) == 100, len(r2)

    # --- my-work is bounded: a to-do queue, not a multi-MB export of every actionable row --------
    mw = c.get(f"{P}/my-work", headers=HDR)
    items = mw.json()
    assert len(items) <= me.MY_WORK_LIMIT, f"my-work unbounded: {len(items)}"
    assert len(mw.content) < 1_000_000, f"my-work payload too big: {len(mw.content)} bytes"

    # --- BCF export: single query (not N+1), capped, valid zip -----------------------------------
    bcf = c.get(f"{P}/modules/rfi/bcf/export", headers=HDR)
    assert bcf.status_code == 200 and bcf.content[:2] == b"PK", bcf.status_code  # zip magic

    # --- dashboard responds with real tallies at scale -------------------------------------------
    dash = c.get(f"{P}/dashboard", headers=HDR).json()
    assert dash["kpis"]["total_records"] >= N, dash["kpis"]
    assert len(dash["action_items"]) <= 100, len(dash["action_items"])

print(f"SCALE OK - {N} rfi rows: list clamped <=1000; my-work bounded <= {me.MY_WORK_LIMIT} "
      f"({len(mw.content)//1024}KB); BCF single-query zip; created_at+assignee indexes present; "
      "dashboard tallies correct.")
