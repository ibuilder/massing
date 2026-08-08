"""R39-VIEWER-OBS — the viewer load-timing intake and its p50/p95 aggregate.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_viewer_load_timing.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_viewer_load_timing.db"
os.environ["STORAGE_DIR"] = "./test_storage_viewer_load_timing"
os.environ.pop("AEC_RBAC", None)

if os.path.exists("./test_viewer_load_timing.db"):
    os.remove("./test_viewer_load_timing.db")

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.routers import standards  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# --- authz, asked of the ROUTE rather than over HTTP ----------------------------------------------
# `AEC_RBAC` is popped above, as every suite here does, so an HTTP probe would come back 200 whether
# or not the dependency exists — it would pass for the wrong reason and keep passing if someone
# deleted the guard. This repo has already been bitten by the mirror image of that: with middleware
# armed, guarded and unguarded routes both 401. So ask the route what it depends on.
#
# It matters specifically here because both routes are `/projects/{pid}/...`. A project-scoped route
# with no role check takes its project id from whoever calls it.
def _dep_names(path: str, method: str) -> str:
    for r in standards.router.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set()):
            return " ".join(repr(d.call) for d in r.dependant.dependencies)
    return ""


for path, method in [("/projects/{pid}/model/load-timing", "POST"),
                     ("/projects/{pid}/model/load-timings", "GET")]:
    deps = _dep_names(path, method)
    check(f"{method} {path} carries a role check", "require_role" in deps or "_role" in deps,
          deps[:160] or "ROUTE NOT FOUND")

# A control: prove `_dep_names` can come back empty, so the assertions above are not passing because
# the helper always returns something containing the word.
check("the dependency probe can return nothing", _dep_names("/no/such/route", "GET") == "")

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Obs"}).json()["id"]

    # --- the intake clamps a hostile client -------------------------------------------------------
    # The poster is a browser, so every number is attacker-controlled. An unclamped total_ms poisons
    # every percentile the table exists to report — a quiet way to make the instrument lie.
    r = c.post(f"/projects/{pid}/model/load-timing", json={
        "modelId": "m", "bucket": "1-10MB", "outcome": "ok",
        "totalMs": 10 ** 12,        # a year of milliseconds
        "fetchMs": -5,              # negative
        "parseMs": True,            # bool is an int in Python — must not sneak through
        "canvasW": 800, "canvasH": 600, "bytes": 1234,
    })
    check("intake accepts a hostile payload without erroring", r.status_code == 200, r.text)

    # NaN deserves its own post, and the reason is worth recording. `httpx` REFUSES to encode NaN, so
    # the obvious test cannot be written — which reads like "NaN cannot arrive". It can: Python's
    # `json.loads` accepts a bare `NaN` literal by default, so a client that writes its own body
    # rather than using JSON.stringify gets one straight through the parser and into the column.
    raw = c.post(f"/projects/{pid}/model/load-timing",
                 content=b'{"bucket": "1-10MB", "outcome": "ok", "firstFrameMs": NaN}',
                 headers={"Content-Type": "application/json"})
    check("a raw NaN body is accepted by the JSON parser (so the guard is load-bearing)",
          raw.status_code == 200, raw.text)

    from aec_api.db import SessionLocal  # noqa: E402
    from aec_api.models import ViewerLoadTiming  # noqa: E402

    with SessionLocal() as db:
        row = db.query(ViewerLoadTiming).first()
        check("an out-of-range duration is dropped, not stored", row.total_ms is None, str(row.total_ms))
        check("a negative duration is dropped", row.fetch_ms is None, str(row.fetch_ms))
        check("a bool does not pass as a duration", row.parse_ms is None, str(row.parse_ms))
        nan_row = db.query(ViewerLoadTiming).order_by(ViewerLoadTiming.ts.desc()).first()
        check("NaN never reaches the column", nan_row.first_frame_ms is None, str(nan_row.first_frame_ms))
        check("a legitimate value in the same payload SURVIVES", row.canvas_w == 800, str(row.canvas_w))

    # An unknown outcome must not become a new category — the aggregate keys off this column.
    c.post(f"/projects/{pid}/model/load-timing", json={"outcome": "excellent", "bucket": "1-10MB"})
    with SessionLocal() as db:
        vals = {r.outcome for r in db.query(ViewerLoadTiming).all()}
        check("an unrecognised outcome is coerced, not stored", vals == {"ok"}, str(vals))

    # --- percentiles ------------------------------------------------------------------------------
    pid2 = c.post("/projects", json={"name": "Obs2"}).json()["id"]
    for i in range(1, 101):
        c.post(f"/projects/{pid2}/model/load-timing",
               json={"bucket": "10-50MB", "outcome": "ok", "totalMs": i})
    agg = c.get(f"/projects/{pid2}/model/load-timings").json()
    band = next(b for b in agg["buckets"] if b["bucket"] == "10-50MB")
    check("p50 is the nearest-rank median", band["p50_ms"] == 50, str(band["p50_ms"]))
    check("p95 is the nearest-rank 95th", band["p95_ms"] == 95, str(band["p95_ms"]))
    check("loads are counted", band["loads"] == 100, str(band["loads"]))

    # --- the survivorship guard -------------------------------------------------------------------
    # A band whose loads mostly stall would otherwise show a superb p95 drawn from its few survivors.
    # `ok_rate` is what stops that reading as good news, so assert the two move independently.
    pid3 = c.post("/projects", json={"name": "Obs3"}).json()["id"]
    c.post(f"/projects/{pid3}/model/load-timing",
           json={"bucket": ">200MB", "outcome": "ok", "totalMs": 10})
    for _ in range(9):
        c.post(f"/projects/{pid3}/model/load-timing", json={"bucket": ">200MB", "outcome": "stalled"})
    b3 = c.get(f"/projects/{pid3}/model/load-timings").json()["buckets"][0]
    check("a band of stalls still reports a fast p95 from its survivor", b3["p95_ms"] == 10, str(b3))
    check("...and ok_rate exposes it as 1 load in 10", b3["ok_rate"] == 0.1, str(b3["ok_rate"]))
    check("stalls are counted separately", b3["stalled"] == 9, str(b3["stalled"]))

    # --- `invisible` survives the round trip ------------------------------------------------------
    # The outcome this whole item exists for. Asserted through the READ path, not by inspecting the
    # row we just wrote: a writer and reader that agree on a wrong format both pass.
    pid4 = c.post("/projects", json={"name": "Obs4"}).json()["id"]
    c.post(f"/projects/{pid4}/model/load-timing",
           json={"bucket": "1-10MB", "outcome": "invisible", "totalMs": 42, "canvasW": 0, "canvasH": 493})
    b4 = c.get(f"/projects/{pid4}/model/load-timings").json()["buckets"][0]
    check("an invisible load is reported as invisible", b4["invisible"] == 1, str(b4))
    check("an invisible load does NOT count towards ok_rate", b4["ok_rate"] == 0.0, str(b4["ok_rate"]))
    check("but it DOES count towards the percentiles — it took real time", b4["p50_ms"] == 42, str(b4))

    # --- retention --------------------------------------------------------------------------------
    with SessionLocal() as db:
        old = ViewerLoadTiming(project_id=pid4, outcome="ok", bucket="1-10MB", total_ms=7)
        old.ts = datetime.now(timezone.utc) - timedelta(days=200)
        db.add(old)
        db.commit()
    before = c.get(f"/projects/{pid4}/model/load-timings?days=365").json()["loads"]
    check("the 200-day-old row is visible before a prune runs", before == 2, str(before))
    c.post(f"/projects/{pid4}/model/load-timing", json={"bucket": "1-10MB", "outcome": "ok", "totalMs": 9})
    # Count alone cannot decide this. 2 -> 2 is what a working prune plus a working insert looks
    # like, and it is EQUALLY what a silently-failed insert plus no prune looks like. Two different
    # states rendering identically is not a check, so name the rows.
    with SessionLocal() as db:
        left = sorted(r.total_ms for r in db.query(ViewerLoadTiming)
                      .filter(ViewerLoadTiming.project_id == pid4).all())
    check("the row past the window is gone", 7 not in left, str(left))
    check("...and the write that triggered the prune landed", 9 in left, str(left))
    check("...leaving the in-window rows untouched", left == [9, 42], str(left))

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("test_viewer_load_timing OK")
