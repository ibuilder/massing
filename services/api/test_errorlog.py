"""Error-log observability: engine record/recent/stats/prune, the global 500 handler, the
client-error intake, and the admin feed. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_errorlog.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_errorlog.db"
os.environ["STORAGE_DIR"] = "./test_storage_errorlog"
os.environ["AEC_LOCAL_MODE"] = "1"          # single-operator mode → admin feed is open (no IdP in tests)
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_errorlog.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import errorlog  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.main import app  # noqa: E402

init_db()

# --- engine: record + recent + stats ---
db = SessionLocal()
try:
    eid = errorlog.record(db, source="server", level="error",
                          exc=ValueError("bad thing"), method="GET", path="/x", status=500,
                          actor="alice", request_id="req-1")
    assert eid, "record returned an id"
    errorlog.record(db, source="web", level="error", kind="TypeError",
                    message="undefined is not a function", path="/app", actor="bob")
    rows = errorlog.recent(db, limit=10)
    assert len(rows) == 2, len(rows)
    assert rows[0]["message"] and rows[0]["ts"], rows[0]
    srv = errorlog.recent(db, limit=10, source="server")
    assert len(srv) == 1 and srv[0]["kind"] == "ValueError", srv
    assert srv[0]["traceback"] and "ValueError" in srv[0]["traceback"], "server row keeps a traceback"
    web = errorlog.recent(db, limit=10, source="web")
    assert len(web) == 1 and web[0]["kind"] == "TypeError", web
    st = errorlog.stats(db)
    assert st["total"] == 2 and st["by_source"] == {"server": 1, "web": 1}, st
    print(f"engine: recorded 2 ({st['by_source']}), traceback captured, filters work")

    # --- retention prune: keep newest N ---
    for i in range(30):
        errorlog.record(db, source="server", message=f"e{i}")
    dropped = errorlog.prune(db, max_rows=10, max_days=30)
    kept = errorlog.stats(db)["total"]
    assert kept == 10, (kept, dropped)
    print(f"prune: trimmed to {kept} rows (dropped {dropped})")
finally:
    db.close()

# --- global 500 handler: unhandled exception → recorded server row + clean 500 + request id ---
app.add_api_route("/__test_boom__", lambda: (_ for _ in ()).throw(RuntimeError("boom-42")), methods=["GET"])
with TestClient(app, raise_server_exceptions=False) as c:
    r = c.get("/__test_boom__")
    assert r.status_code == 500, r.status_code
    body = r.json()
    assert body.get("request_id"), body
    assert r.headers.get("X-Request-ID") == body["request_id"], r.headers
    # a normal request also carries the request-id header
    assert c.get("/health").headers.get("X-Request-ID"), "request-id on every response"

db = SessionLocal()
try:
    boom = [e for e in errorlog.recent(db, limit=50, source="server") if e["kind"] == "RuntimeError"]
    assert boom and boom[0]["path"] == "/__test_boom__" and boom[0]["status"] == 500, boom[:1]
    assert boom[0]["request_id"], "500 handler stamped the request id on the row"
    print(f"500 handler: recorded {boom[0]['kind']} at {boom[0]['path']} (rid={boom[0]['request_id']})")
finally:
    db.close()

# --- client-error intake + admin feed + prune endpoint ---
with TestClient(app) as c:
    r = c.post("/client-errors", json={"message": "render crashed", "kind": "ViewerError",
                                       "path": "/app/model", "detail": {"guid": "abc"}})
    assert r.status_code == 200 and r.json()["recorded"], r.text[:200]
    feed = c.get("/admin/errors?source=web&limit=5")
    assert feed.status_code == 200, feed.text[:200]
    j = feed.json()
    assert any(e["kind"] == "ViewerError" and e["message"] == "render crashed" for e in j["errors"]), j
    assert "stats" in j and j["stats"]["total"] >= 1, j
    # housekeeping prune endpoint
    assert c.delete("/admin/errors").status_code == 200
print("test_errorlog OK")
