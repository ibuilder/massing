"""MEETINGS (closeout) — action items now link to RFIs and issues, not just their meeting. This closes
the last MEETINGS sub-item: a flagged action item captured in minutes can trace to the RFI or issue it
concerns, and that record shows the action as an incoming reference.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_meeting_links.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_meeting_links.db"
os.environ["STORAGE_DIR"] = "./test_storage_meetlinks"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_meeting_links.db"):
    os.remove("./test_meeting_links.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules_registry as mr  # noqa: E402
from aec_api.main import app  # noqa: E402

# the action_item module now references meeting + rfi + issue
mr.load_registry()
refs = {f["name"]: f.get("module") for f in mr.REGISTRY["action_item"]["fields"] if f["type"] == "reference"}
assert refs.get("linked_rfi") == "rfi" and refs.get("linked_issue") == "issue", refs

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Meeting Links"}).json()["id"]

    rfi = c.post(f"/projects/{pid}/modules/rfi",
                 json={"data": {"subject": "Beam pocket conflict", "question": "Confirm pocket depth?"}}).json()
    iss = c.post(f"/projects/{pid}/modules/issue", json={"data": {"subject": "Grid B clash"}}).json()
    assert "id" in rfi and "id" in iss, (rfi, iss)

    # an action item captured from minutes, linked to both the RFI and the issue
    ai = c.post(f"/projects/{pid}/modules/action_item",
                json={"data": {"subject": "Resolve beam pocket per RFI", "assignee": "EOR",
                               "priority": "High", "linked_rfi": rfi["id"], "linked_issue": iss["id"]}})
    assert ai.status_code == 201, ai.text[:200]
    aij = ai.json()
    # the create resolves the reference fields into clickable briefs
    dr = aij.get("data_refs") or {}
    assert dr.get("linked_rfi", {}).get("id") == rfi["id"], dr
    assert dr.get("linked_issue", {}).get("id") == iss["id"], dr

    # the RFI's related view lists the action item as an incoming reference
    rel = c.get(f"/projects/{pid}/modules/rfi/{rfi['id']}/related").json()
    incoming_ids = [r.get("id") for r in rel.get("incoming", [])]
    assert aij["id"] in incoming_ids, rel
    # same for the issue
    rel_i = c.get(f"/projects/{pid}/modules/issue/{iss['id']}/related").json()
    assert aij["id"] in [r.get("id") for r in rel_i.get("incoming", [])], rel_i

print("MEETINGS OK - action items now link to RFIs and issues (not just the meeting): a minutes action "
      "item linked to an RFI + an issue resolves both into clickable briefs, and each of the RFI and the "
      "issue shows the action item as an incoming reference — closing the last MEETINGS sub-item.")
