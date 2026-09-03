"""Cross-module due/overdue SLA feed — open records past or near their due date are bucketed;
terminal (closed) records and far-future ones are excluded.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_due_feed.py"""
import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_duefeed.db"
os.environ["STORAGE_DIR"] = "./test_storage_duefeed"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_duefeed.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

today = date.today()
PAST = (today - timedelta(days=3)).isoformat()
SOON = (today + timedelta(days=2)).isoformat()
FAR = (today + timedelta(days=60)).isoformat()


def mk_rfi(c, pid, subj, due):
    return c.post(f"/projects/{pid}/modules/rfi",
                  json={"data": {"subject": subj, "question": "?", "due_date": due}}).json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "SLA"}).json()["id"]
    overdue_id = mk_rfi(c, pid, "Overdue RFI", PAST)
    mk_rfi(c, pid, "Due-soon RFI", SOON)
    mk_rfi(c, pid, "Far RFI", FAR)
    # a closed (terminal) RFI with a past due date must NOT appear
    closed = mk_rfi(c, pid, "Closed RFI", PAST)
    c.patch(f"/projects/{pid}/modules/rfi/{closed}", json={"answer": "done"})
    for action in ("submit", "respond", "accept"):
        c.post(f"/projects/{pid}/modules/rfi/{closed}/transition", json={"action": action})

    feed = c.get(f"/projects/{pid}/due-feed?days=7").json()
    assert feed["counts"]["overdue"] == 1, feed["counts"]
    assert feed["counts"]["due_soon"] == 1, feed["counts"]
    refs_overdue = [x["title"] for x in feed["overdue"]]
    assert refs_overdue == ["Overdue RFI"], refs_overdue
    assert feed["overdue"][0]["days"] < 0 and feed["due_soon"][0]["days"] >= 0, feed
    # far-future + closed are both excluded
    titles = [x["title"] for x in feed["overdue"] + feed["due_soon"]]
    assert "Far RFI" not in titles and "Closed RFI" not in titles, titles
    # a wider horizon pulls the far one into due-soon
    wide = c.get(f"/projects/{pid}/due-feed?days=90").json()
    assert wide["counts"]["due_soon"] == 2, wide["counts"]

print(f"DUE-FEED OK - {feed['counts']['overdue']} overdue + {feed['counts']['due_soon']} due-soon (7d); "
      "closed + far-future excluded; horizon widens the window")
