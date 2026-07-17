"""FIN-TEST: the change-order log analytics (co_log) — CO value pipeline by state (pending/approved/
executed/rejected), schedule-day exposure excluding rejected, ball-in-court, and upstream change-event ROM
exposure. DB-backed; states set directly to test the aggregation math, not the workflow machinery.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_changeorders.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_changeorders_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_changeorders")
os.environ.pop("AEC_RBAC", None)
_db = os.environ["DATABASE_URL"]
if _db.startswith("sqlite:///./"):
    try:
        _f = _db[len("sqlite:///./"):]
        if os.path.exists(_f):
            os.remove(_f)
    except OSError:
        pass

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import update  # noqa: E402

from aec_api import changeorders  # noqa: E402
from aec_api import modules as me  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402

H = {"X-User": "gc"}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "CO Log"}).json()["id"]

    def cor(amount, state, reason="Design change", schedule_days=0.0, subject="CO"):
        r = c.post(f"/projects/{pid}/modules/cor",
                   json={"data": {"subject": subject, "amount": amount, "reason": reason,
                                  "schedule_days": schedule_days}}, headers=H).json()
        return r["id"]

    ids = {
        "draft": cor(10000, "draft", reason="Design change", schedule_days=5),
        "submitted": cor(20000, "submitted", reason="Field condition", schedule_days=3),
        "approved": cor(30000, "approved", reason="Design change", schedule_days=2),
        "executed": cor(40000, "executed", reason="Owner request", schedule_days=4),
        "rejected": cor(50000, "rejected", reason="Design change", schedule_days=10),   # sched excluded
    }
    # set the terminal states directly (skip the party-gated transitions — we're testing the math)
    with SessionLocal() as db:
        t = me.TABLES["cor"]
        for state, rid in ids.items():
            db.execute(update(t).where(t.c.id == rid).values(workflow_state=state))
        db.commit()

    # a couple of upstream change events (ROM exposure = open ones only)
    def ce(rom, state="open", scope="Undetermined"):
        r = c.post(f"/projects/{pid}/modules/change_event",
                   json={"data": {"subject": "CE", "rom": rom, "scope_status": scope}}, headers=H).json()
        return r["id"]
    ce_open = ce(100000, scope="In scope")
    ce_closed = ce(50000)
    with SessionLocal() as db:
        t = me.TABLES["change_event"]
        db.execute(update(t).where(t.c.id == ce_closed).values(workflow_state="closed"))
        db.commit()

    with SessionLocal() as db:
        log = changeorders.co_log(db, pid)

    assert log["co_count"] == 5, log["co_count"]
    assert log["total_value"] == 150000.0, log["total_value"]                     # 10+20+30+40+50 k
    assert log["pending_value"] == 30000.0, log["pending_value"]                  # draft 10k + submitted 20k
    assert log["approved_value"] == 30000.0, log["approved_value"]
    assert log["executed_value"] == 40000.0, log["executed_value"]
    assert log["rejected_value"] == 50000.0, log["rejected_value"]
    # schedule days sum EXCLUDES the rejected CO's 10 days: 5+3+2+4 = 14
    assert log["total_schedule_days"] == 14.0, log["total_schedule_days"]
    # ball-in-court mapping (one per state)
    assert log["ball_in_court"] == {"GC (prepare)": 1, "Owner / Architect": 1, "GC (execute)": 1,
                                    "Executed": 1, "Rejected": 1}, log["ball_in_court"]
    # reason mix (sorted): Design change ×3, Field condition ×1, Owner request ×1
    assert log["by_reason"] == {"Design change": 3, "Field condition": 1, "Owner request": 1}, log["by_reason"]
    # upstream change events: only the open one contributes ROM exposure
    assert log["change_events_open"] == 1 and log["change_event_rom_exposure"] == 100000.0, log

    print("CHANGEORDERS OK - co_log aggregates the CO pipeline: total 150k = pending 30k (draft+submitted) + "
          "approved 30k + executed 40k + rejected 50k; schedule-day exposure sums 14 days EXCLUDING the "
          "rejected CO's 10; ball-in-court maps each state to its court; reason mix counted; upstream "
          "change-event ROM exposure counts only open events (100k), the closed one excluded.")
