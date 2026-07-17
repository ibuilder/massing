"""Distribution lists: a record's CC field resolves against the contact directory, and the resolved
emails ride the transition webhook. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_distribution.py"""
import json
import os

# setdefault so the parallel runner's unique per-test db (cleaned each run) wins; fixed names standalone
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_dist.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_dist")
os.environ.pop("AEC_RBAC", None)
os.environ["AEC_WEBHOOK_URLS"] = "http://hook.example/x"
os.environ["AEC_WEBHOOK_SYNC"] = "1"
_dburl = os.environ["DATABASE_URL"]
if _dburl.startswith("sqlite:///./"):
    try:                                     # a lingering Windows file lock must not crash import
        _f = _dburl[len("sqlite:///./"):]
        if os.path.exists(_f):
            os.remove(_f)
    except OSError:
        pass

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import webhooks  # noqa: E402
from aec_api.main import app  # noqa: E402

SENT: list = []
webhooks._send = lambda url, body: SENT.append(json.loads(body))   # type: ignore


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Dist"}).json()["id"]
    mk(c, pid, "contact", {"name": "Jane Doe", "email": "jane@x.com"})
    rid = mk(c, pid, "rfi", {"subject": "Beam", "question": "size?",
                             "distribution": "Jane Doe, bob@y.com, Ghost Person"})

    d = c.get(f"/projects/{pid}/modules/rfi/{rid}/distribution").json()
    byname = {r["name"]: r for r in d["recipients"]}
    assert byname["Jane Doe"]["email"] == "jane@x.com" and byname["Jane Doe"]["resolved"], d
    assert byname["bob@y.com"]["email"] == "bob@y.com" and byname["bob@y.com"]["resolved"], d
    assert byname["Ghost Person"]["resolved"] is False, d         # not in directory
    assert set(d["emails"]) == {"jane@x.com", "bob@y.com"}, d["emails"]

    # the transition webhook carries the resolved distribution
    SENT.clear()
    c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", json={"action": "submit"})
    assert SENT and SENT[0]["event"] == "record.transition", SENT
    assert set(SENT[0]["distribution"]) == {"jane@x.com", "bob@y.com"}, SENT[0].get("distribution")

print("DISTRIBUTION OK - CC field resolves names->directory emails + raw emails (Ghost unresolved); "
      "resolved emails ride the record.transition webhook")
