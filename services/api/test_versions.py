"""Model version history + diff: snapshot GUID sets per publish, list, diff (added/removed).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_versions.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./versions_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_ver"
os.environ.pop("AEC_RBAC", None)
for f in ("./versions_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api import versions  # noqa: E402


def idx(*guids):
    return {"elements": [{"guid": g} for g in guids], "counts": {"elements": len(guids)}}


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Versioned"}).json()["id"]

    s1 = versions.snapshot(pid, idx("A", "B", "C"))
    assert s1["version"] == 1 and s1["element_count"] == 3, s1
    s2 = versions.snapshot(pid, idx("B", "C", "D"))            # +D, -A
    assert s2["version"] == 2 and s2["added"] == 1 and s2["removed"] == 1, s2
    # an identical republish is skipped (history stays meaningful)
    s3 = versions.snapshot(pid, idx("B", "C", "D"))
    assert s3.get("skipped"), s3

    hist = c.get(f"/projects/{pid}/versions").json()
    assert [h["version"] for h in hist] == [2, 1], hist     # newest first
    assert hist[0]["element_count"] == 3 and hist[0]["note"] == "+1/-1", hist[0]

    d = c.get(f"/projects/{pid}/versions/diff?a=1&b=2").json()
    assert d["added"] == ["D"] and d["removed"] == ["A"] and d["unchanged_count"] == 2, d

    print("VERSIONS OK - snapshot per publish (A,B,C -> B,C,D), no-op skipped, history newest-first, diff +D/-A")
