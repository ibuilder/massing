"""TOPIC-LIFE — the BCF-topic lifecycle spine: the status state machine on PATCH (invalid moves 422,
reopen paths work, vendor statuses pass through), threaded comments (reply_to validated to the same
topic), and the merged per-topic timeline (creation → status moves → comments → allowed_next).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_topic_lifecycle.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_topic_lifecycle.db"
os.environ["STORAGE_DIR"] = "./test_storage_topiclife"
os.environ.pop("AEC_RBAC", None)

if os.path.exists("./test_topic_lifecycle.db"):
    os.remove("./test_topic_lifecycle.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Life"}).json()["id"]
    tid = c.post(f"/projects/{pid}/topics",
                 json={"type": "rfi", "title": "Beam clearance at L3"}).json()["id"]

    # --- the state machine: legal path open → in progress → resolved → closed ---------------------
    def move(status):
        return c.patch(f"/projects/{pid}/topics/{tid}", json={"status": status})

    assert move("in progress").status_code == 200
    assert move("resolved").status_code == 200
    r = move("open")                                     # resolved can NOT go straight back to open
    assert r.status_code == 422 and "invalid status transition" in r.json()["detail"], r.text
    assert move("resolved").status_code == 200           # idempotent same-status PATCH is a no-op
    assert move("closed").status_code == 200
    assert move("resolved").status_code == 422           # closed only reopens to "in progress"
    assert move("in progress").status_code == 200        # the reopen path
    # vendor/BCF-import statuses outside the canonical set pass through unvalidated (round-trip compat)
    assert move("UnderReviewByOwner").status_code == 200
    assert move("closed").status_code == 200             # ...and leaving a vendor status is free

    # --- threaded comments: reply_to must name a comment on THIS topic ----------------------------
    root = c.post(f"/projects/{pid}/topics/{tid}/comments",
                  json={"author": "sara", "text": "Need 150mm clearance."}).json()
    reply = c.post(f"/projects/{pid}/topics/{tid}/comments",
                   json={"author": "lee", "text": "Confirmed on site.", "reply_to": root["id"]})
    assert reply.status_code == 201 and reply.json()["reply_to"] == root["id"], reply.text
    assert c.post(f"/projects/{pid}/topics/{tid}/comments",
                  json={"text": "x", "reply_to": "nope"}).status_code == 422
    other = c.post(f"/projects/{pid}/topics", json={"type": "info", "title": "Other"}).json()["id"]
    assert c.post(f"/projects/{pid}/topics/{other}/comments",
                  json={"text": "cross-topic", "reply_to": root["id"]}).status_code == 422, \
        "a reply must not thread onto a comment from another topic"
    listed = c.get(f"/projects/{pid}/topics/{tid}/comments").json()
    assert [x.get("reply_to") for x in listed] == [None, root["id"]], listed

    # --- the merged timeline: creation → status moves → comments, oldest→newest -------------------
    tl = c.get(f"/projects/{pid}/topics/{tid}/timeline").json()
    kinds = [e["kind"] for e in tl["events"]]
    assert kinds[0] == "created" and "Beam clearance" in tl["events"][0]["summary"], tl["events"][0]
    statuses = [e["summary"] for e in tl["events"] if e["kind"] == "status"]
    assert statuses[0] == "status → in progress" and statuses[-1] == "status → closed", statuses
    comments = [e for e in tl["events"] if e["kind"] == "comment"]
    assert len(comments) == 2 and comments[1]["detail"]["reply_to"] == root["id"], comments
    assert tl["status"] == "closed" and tl["allowed_next"] == ["in progress"], tl
    assert tl["statuses"] == ["open", "in progress", "resolved", "closed"]
    assert c.get(f"/projects/{pid}/topics/nope/timeline").status_code == 404

print("TOPIC-LIFE OK - the canonical status machine is enforced on PATCH (resolved cannot jump back "
      "to open, closed only reopens to 'in progress', idempotent PATCH passes, vendor BCF statuses "
      "pass through for round-trip compatibility); comments thread via reply_to (validated to an "
      "existing comment on the SAME topic, cross-topic threading 422s); and the merged per-topic "
      "timeline replays creation, every status move, and the threaded comments oldest-to-newest with "
      "the canonical status list + this topic's allowed next transitions.")
