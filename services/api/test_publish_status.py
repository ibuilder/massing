"""Publish pipeline queue-readiness — run_publish is a synchronous worker-callable task, status is
durable, and an interrupted ("running" but stale) job is reported as an error (not stuck forever).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_publish_status.py"""
import json
import os
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_pubstatus.db"
os.environ["STORAGE_DIR"] = "./test_storage_pubstatus"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_pubstatus.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient                    # noqa: E402
from aec_api.main import app                                 # noqa: E402
from aec_api import storage                                  # noqa: E402
from aec_api.routers.authoring import run_publish            # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Publish"}).json()["id"]

    # run_publish is directly callable (the future worker entrypoint) and always terminates the
    # status — with no source IFC it ends in error/done, never stuck "running".
    run_publish(pid)
    st = c.get(f"/projects/{pid}/publish/status").json()
    assert st["state"] in ("error", "done"), st

    key = f"{pid}/publish_status.json"
    # a stale "running" (worker died / server restarted) is recovered as an interrupted error
    storage.put(key, json.dumps({"state": "running", "detail": None,
                                 "at": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()}).encode())
    st2 = c.get(f"/projects/{pid}/publish/status").json()
    assert st2["state"] == "error" and "interrupted" in st2["detail"]["error"], st2

    # a fresh "running" is left alone
    storage.put(key, json.dumps({"state": "running", "detail": None,
                                 "at": datetime.now(timezone.utc).isoformat()}).encode())
    assert c.get(f"/projects/{pid}/publish/status").json()["state"] == "running"

print("PUBLISH STATUS OK - run_publish is worker-callable + always terminates status; stale 'running' "
      "recovered as interrupted error; fresh 'running' preserved (no Celery needed)")
