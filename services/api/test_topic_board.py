"""TOPIC-BOARD — kanban columns over the BCF topics (stable workflow order) + QUERY-DSL smart filters over
topic fields. Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_topic_board.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_topic_board.db"
os.environ["STORAGE_DIR"] = "./test_storage_topicboard"
os.environ.pop("AEC_RBAC", None)

from aec_api import topic_board as tb  # noqa: E402

topics = [
    {"title": "Duct clash L3", "status": "open", "priority": "High", "assignee": "kim", "type": "clash",
     "modified_at": "2026-07-20T10:00:00"},
    {"title": "Missing fire rating", "status": "open", "priority": "Low", "assignee": "kim", "type": "rfi",
     "modified_at": "2026-07-22T10:00:00"},
    {"title": "Rework slab edge", "status": "closed", "priority": "High", "assignee": None, "type": "punch",
     "modified_at": "2026-07-19T10:00:00"},
    {"title": "Door hardware", "status": "in progress", "priority": None, "assignee": "lee", "type": "rfi",
     "modified_at": "2026-07-21T10:00:00"},
]

# --- grouping: stable workflow order + newest-modified first within a column ------------------------
b = tb.board(topics, "status")
assert b["total"] == 4 and [c["key"] for c in b["columns"]] == ["open", "in progress", "closed"], b["columns"]
open_col = b["columns"][0]
assert open_col["count"] == 2 and open_col["topics"][0]["title"] == "Missing fire rating", open_col

# priority order + (unassigned) last
p = tb.board(topics, "priority")
assert [c["key"] for c in p["columns"]] == ["High", "Low", "(unassigned)"], p["columns"]
a = tb.board(topics, "assignee")
assert [c["key"] for c in a["columns"]][-1] == "(unassigned)", a["columns"]

# --- QUERY-DSL smart filters over topic fields ------------------------------------------------------
f = tb.board(topics, "status", "priority=High")
assert f["total"] == 2 and {c["key"] for c in f["columns"]} == {"open", "closed"}, f
f2 = tb.board(topics, "status", "status=open & assignee=kim")
assert f2["total"] == 2, f2
f3 = tb.board(topics, "status", "title~duct")
assert f3["total"] == 1 and f3["columns"][0]["topics"][0]["title"] == "Duct clash L3", f3

try:
    tb.board(topics, "nonsense")
    raise AssertionError("bad group_by must raise")
except ValueError:
    pass

# --- route: /topics/board must NOT be captured by /topics/{tid} ------------------------------------
if os.path.exists("./test_topic_board.db"):
    os.remove("./test_topic_board.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Board"}).json()["id"]
    for t in [{"type": "clash", "title": "Duct clash L3", "status": "open", "priority": "High"},
              {"type": "rfi", "title": "Missing fire rating", "status": "open"},
              {"type": "punch", "title": "Rework slab edge", "status": "closed"}]:
        assert c.post(f"/projects/{pid}/topics", json=t).status_code == 201
    rr = c.get(f"/projects/{pid}/topics/board")
    assert rr.status_code == 200, rr.text                                  # NOT a 404 from /topics/{tid}
    j = rr.json()
    assert j["total"] == 3 and j["columns"][0]["key"] == "open" and j["columns"][0]["count"] == 2, j
    flt = c.get(f"/projects/{pid}/topics/board", params={"filter": "priority=High"})
    assert flt.status_code == 200 and flt.json()["total"] == 1, flt.text
    assert c.get(f"/projects/{pid}/topics/board", params={"group_by": "nope"}).status_code == 422
    assert c.get(f"/projects/{pid}/topics/board", params={"filter": "& &"}).status_code == 422
    # a term with no operator is LEGAL grammar (a field-exists check) — it filters, never 500s
    assert c.get(f"/projects/{pid}/topics/board", params={"filter": "priority"}).json()["total"] == 1

print("TOPIC-BOARD OK - the kanban groups topics into stable workflow-ordered columns (open → in progress → "
      "closed; priority High → Low with unassigned last; newest-modified first within a column) and the "
      "QUERY-DSL grammar filters topic fields (priority=High → 2, status=open & assignee=kim → 2, title~duct "
      "→ 1); the /topics/board route resolves ahead of /topics/{tid} (200 not 404), applies filters "
      "server-side, and 422s on a bad group_by or an unparseable selector.")
