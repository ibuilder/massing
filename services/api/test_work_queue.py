"""R26-WORK-QUEUE — what is in your court, in the order it needs you, actionable in place.

The Work room's whole job. Both halves already existed — `my_work` knows what is in your court and
`due_feed` knows what is late — but as separate lists on separate screens, neither carrying the thing
that turns a list into a queue: what you can do about each item without leaving it.

Two properties are what make it worth having, and both are tested below.

**`undated` is not `later`.** An item nobody dated is a gap somebody should close, not a low
priority. Folding it into "later" would sort an urgent dateless RFI below a routine item due next
month, and would hide the gap that caused it.

**The actions offered are the ones the engine will honour** — this party, from this state. A queue
that offers a button the API then rejects spends the user's trust before it spends their time.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_work_queue.py
"""
import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_work_queue.db"
os.environ["STORAGE_DIR"] = "./test_storage_work_queue"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_work_queue.db"):
    os.remove("./test_work_queue.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import work_queue as wq  # noqa: E402
from aec_api.main import app  # noqa: E402

HDR = {"X-User": "gc"}
T = date(2026, 7, 25)

# ---- bucketing: the whole point is that ABSENT is its own answer -----------------------------------
assert wq.bucket("2026-07-24", T) == "overdue"
assert wq.bucket("2026-07-25", T) == "today"
assert wq.bucket("2026-07-30", T) == "soon"
assert wq.bucket("2026-08-30", T) == "later"

# absent, blank and unparseable all mean "the platform does not know when this is due" — which is
# `undated`, never `later`. Treating an unreadable date as far-future would bury the item AND the
# defect that produced it.
for bad in (None, "", "   ", "not-a-date", "2026-13-45", 12345):
    assert wq.bucket(bad, T) == "undated", bad

# an ISO datetime still buckets on its date part
assert wq.bucket("2026-07-24T09:30:00Z", T) == "overdue"

# ---- the bucket ORDER puts undated above later ----------------------------------------------------
assert wq.BUCKETS == ["overdue", "today", "soon", "undated", "later"]
assert wq.BUCKETS.index("undated") < wq.BUCKETS.index("later"), \
    "an item nobody dated needs a decision; burying it under dated work is the failure mode"
for b in wq.BUCKETS:
    assert wq.BUCKET_LABEL[b] and len(wq.BUCKET_MEANS[b]) > 12, b
assert "gap" in wq.BUCKET_MEANS["undated"], "the bucket must say WHY it exists"

# ---- against a real project ------------------------------------------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Queue"}, headers=HDR).json()["id"]

    past = (date.today() - timedelta(days=3)).isoformat()
    soon = (date.today() + timedelta(days=2)).isoformat()
    far = (date.today() + timedelta(days=90)).isoformat()

    # Ask the engine which field carries the due date rather than guessing one. Writing
    # `response_due` here (a plausible name the RFI module does not define) left every record
    # undated, and the queue dutifully reported four undated items — correct behaviour, useless
    # test. A hardcoded field name in a test is a second source of truth about the schema.
    from aec_api import modules as me  # noqa: PLC0415

    due_field = me._due_field_name(me.get_module("rfi"))
    assert due_field, "the RFI module must carry a due-date field for this test to mean anything"

    def rfi(subject, due=None):
        data = {"subject": subject, "question": "?"}
        if due:
            data[due_field] = due
        r = c.post(f"/projects/{pid}/modules/rfi", json={"data": data}, headers=HDR)
        assert r.status_code in (200, 201), r.text
        return r.json()

    late = rfi("Late one", past)
    rfi("Soon one", soon)
    rfi("Far one", far)
    bare = rfi("No date at all")

    q = c.get(f"/projects/{pid}/work-queue", headers=HDR).json()
    by = {b["key"]: b for b in q["buckets"]}

    # every bucket is present even when empty — a queue that hides "Overdue" when it is empty makes
    # the user check whether it was hidden or clean
    assert [b["key"] for b in q["buckets"]] == wq.BUCKETS, q["buckets"]

    assert by["overdue"]["count"] == 1, by["overdue"]
    assert by["overdue"]["items"][0]["ref"] == late["ref"]
    assert by["soon"]["count"] == 1, by["soon"]
    assert by["later"]["count"] == 1, by["later"]
    assert by["undated"]["count"] == 1, by["undated"]
    assert by["undated"]["items"][0]["ref"] == bare["ref"]
    assert q["total"] == 4, q["total"]

    # ---- the actions offered are the ones the ENGINE will honour ---------------------------------
    item = by["overdue"]["items"][0]
    assert item["actions"], item
    # ...proved by running one: a button this queue offers must not 409
    act = item["actions"][0]
    r = c.post(f"/projects/{pid}/modules/rfi/{late['id']}/transition",
               json={"action": act}, headers=HDR)
    assert r.status_code in (200, 201), (act, r.status_code, r.text)

    # ---- an item with no exit is counted separately ----------------------------------------------
    # "You have 14 things" and "you have 14 things and 3 are waiting on somebody else" are different
    # statements, and only the second lets someone plan their day.
    q2 = c.get(f"/projects/{pid}/work-queue", headers=HDR).json()
    assert q2["actionable"] + q2["no_action"] == q2["total"], q2
    assert q2["actionable"] > 0, q2

    # ---- the queue does not invent its own definition of "in my court" ----------------------------
    # A second definition is exactly how two screens come to disagree — the same defect
    # test_consistency exists to prevent, one layer down.
    mine = c.get(f"/projects/{pid}/my-work", headers=HDR).json()
    feed = mine if isinstance(mine, list) else (mine.get("items") or [])
    assert q2["total"] == len(feed), (q2["total"], len(feed))
    assert {i["id"] for b in q2["buckets"] for i in b["items"]} == {i["id"] for i in feed}

print("R26-WORK-QUEUE OK - the ball-in-court feed is now a queue: dated, bucketed by urgency, and "
      "carrying the actions this caller can actually run. Two properties make it worth having. "
      "UNDATED IS NOT LATER - an item nobody dated is a gap somebody should close, not a low "
      "priority, so it gets its own bucket ABOVE 'later'; folding it in would sort an urgent dateless "
      "RFI below a routine item due next month and hide the gap that caused it. An absent, blank or "
      "UNPARSEABLE date all land there too, because an unreadable date means the same thing as a "
      "missing one and treating it as far-future would bury the defect along with the item. And the "
      "actions offered are the ones the ENGINE will honour for this party from this state - proved by "
      "running one against the API rather than asserted - because a queue that offers a button the "
      "server then rejects spends the user's trust before it spends their time. The queue is built ON "
      "my_work rather than beside it and is asserted to return exactly that feed: a second definition "
      "of 'in my court' is how two screens come to disagree.")
