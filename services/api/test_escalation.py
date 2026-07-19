"""WORKFLOW-ENGINE — overdue escalation + explicit ball-in-court on transition.

Covers:
  * transition() moves party_owner to the new state's ball-in-court (RFI open → Consultant/OwnersRep).
  * escalation.scan buckets overdue records by computed level; escalation.run writes an
    `escalation:L{n}` timeline entry that the notifications feed surfaces.
  * idempotency — a second run before the record climbs the next rung escalates nothing new.
  * the escalation_scan job kind round-trips through the durable queue.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_escalation.py"""
import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_escalation.db"
os.environ["STORAGE_DIR"] = "./test_storage_escalation"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_escalation.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

today = date.today()
LATE4 = (today - timedelta(days=4)).isoformat()    # → level 2 (3–6 days)
LATE9 = (today - timedelta(days=9)).isoformat()    # → level 3 (7+ days)
SOON = (today + timedelta(days=2)).isoformat()     # not overdue


def mk_rfi(c, pid, subj, due):
    return c.post(f"/projects/{pid}/modules/rfi",
                  json={"data": {"subject": subj, "question": "?", "due_date": due}}).json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Escalation"}).json()["id"]

    # --- explicit ball-in-court: a fresh RFI (draft) submits into `open`; its court is the responder.
    rid2 = mk_rfi(c, pid, "Ball-in-court RFI", LATE4)
    rec0 = c.get(f"/projects/{pid}/modules/rfi/{rid2}").json()
    assert rec0["workflow_state"] == "draft", rec0["workflow_state"]
    # party_owner at create is the actor's party (None with RBAC off); after submit it tracks the court.
    rec1 = c.post(f"/projects/{pid}/modules/rfi/{rid2}/transition", json={"action": "submit"}).json()
    assert rec1["workflow_state"] == "open", rec1["workflow_state"]
    assert rec1["party_owner"] == "Consultant/OwnersRep", rec1["party_owner"]
    # answer + respond → court becomes the GC (who accepts)
    c.patch(f"/projects/{pid}/modules/rfi/{rid2}", json={"answer": "here"})
    rec2 = c.post(f"/projects/{pid}/modules/rfi/{rid2}/transition", json={"action": "respond"}).json()
    assert rec2["workflow_state"] == "answered" and rec2["party_owner"] == "GC", rec2["party_owner"]

    # --- overdue set: one 4-day-late (L2) + one 9-day-late (L3), both in `open`; one due-soon (excluded)
    late_l2 = mk_rfi(c, pid, "Late L2", LATE4)
    late_l3 = mk_rfi(c, pid, "Late L3", LATE9)
    soon = mk_rfi(c, pid, "Due soon", SOON)
    for r in (late_l2, late_l3, soon):
        c.post(f"/projects/{pid}/modules/rfi/{r}/transition", json={"action": "submit"})

    # scan (read-only): rec2 (answered, LATE4) + the two open ones are all overdue → 3 items.
    scan = c.get(f"/projects/{pid}/escalations").json()
    assert scan["count"] == 3, scan
    levels = {i["title"]: i["level"] for i in scan["items"]}
    assert levels["Late L2"] == 2 and levels["Late L3"] == 3, levels
    assert all(i["needs_escalation"] for i in scan["items"]), scan
    # highest level sorts first
    assert scan["items"][0]["level"] == 3, scan["items"][0]

    # run: writes one escalation:L{n} per record.
    run1 = c.post(f"/projects/{pid}/escalations/run").json()
    assert run1["escalated"] == 3, run1
    assert run1["by_level"].get("3") == 1 and run1["by_level"].get("2") == 2, run1["by_level"]

    # the escalation lands on the record's timeline...
    rec_l3 = c.get(f"/projects/{pid}/modules/rfi/{late_l3}").json()
    esc = [a for a in rec_l3["activity"] if a["action"] == "escalation:L3"]
    assert len(esc) == 1 and esc[0]["party"] == "Consultant/OwnersRep", esc
    assert esc[0]["detail"]["days_overdue"] == 9, esc[0]["detail"]

    # ...and surfaces in the notifications feed for a member whose party is the ball-in-court.
    # (actor is the admin test user; a distinct party sees it as "your move".)
    notifs = c.get(f"/projects/{pid}/notifications").json()
    assert any(n["action"] == "escalation:L3" for n in notifs), notifs

    # idempotent: re-run before anything climbs a rung → nothing new.
    run2 = c.post(f"/projects/{pid}/escalations/run").json()
    assert run2["escalated"] == 0, run2
    scan2 = c.get(f"/projects/{pid}/escalations").json()
    assert scan2["pending"] == 0, scan2

    # the durable job kind round-trips (enqueue → worker → done). Escalation already applied, so it
    # escalates nothing new but must complete cleanly.
    job = c.post(f"/projects/{pid}/jobs", json={"kind": "escalation_scan", "params": {}}).json()
    import time
    for _ in range(50):
        st = c.get(f"/projects/{pid}/jobs/{job['id']}").json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert st["state"] == "done", st
    assert st["result"]["escalated"] == 0, st["result"]

print("ESCALATION OK - ball-in-court tracks transitions (open→Consultant/OwnersRep, answered→GC); "
      "3 overdue escalated (L2×2 + L3×1) onto timelines + notified; idempotent re-run; job round-trips")
