"""Field AI (Phase E): labor productivity analytics (E1) + the feature-flagged CV progress bridge (E2).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_field_ai.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_field_ai.db"
os.environ["STORAGE_DIR"] = "./test_storage_field_ai"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_CV_BRIDGE", None)          # bridge off by default
for _f in ("./test_field_ai.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import cv_bridge, reports  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- E1: labor productivity ------------------------------------------------------------------
    def log(data):
        r = c.post(f"/projects/{pid}/modules/productivity_log", json={"data": data})
        assert r.status_code == 201, r.text[:160]

    log({"date": "2026-03-02", "activity": "SOG pour", "trade": "Concrete",
         "quantity": 120, "unit": "cy", "workers": 6, "hours": 8})     # 120 / 48 mh = 2.5 cy/mh
    log({"date": "2026-03-03", "activity": "SOG pour", "trade": "Concrete",
         "quantity": 90, "unit": "cy", "workers": 6, "hours": 8})      # 90 / 48 mh = 1.875 cy/mh
    log({"date": "2026-03-02", "activity": "Layout", "trade": "Carpentry"})  # no production -> excluded

    s = c.get(f"/projects/{pid}/productivity/summary").json()
    assert s["count"] == 3, s
    conc = next(t for t in s["by_trade"] if t["trade"] == "Concrete")
    assert conc["quantity"] == 210.0 and conc["man_hours"] == 96.0, conc
    assert conc["units_per_manhour"] == round(210 / 96, 3), conc          # ~2.188 cy/man-hr
    assert {t["trade"] for t in s["by_trade"]} == {"Concrete"}, s["by_trade"]   # carpentry has no man-hrs

    rep = c.get(f"/projects/{pid}/reports/productivity.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code
    assert "productivity" in {x["id"] for x in reports.catalog()}

    # --- E2: CV progress bridge is off by default; ingest is a no-op -----------------------------
    st = c.get(f"/projects/{pid}/cv-progress/status").json()
    assert st["enabled"] is False and st["feature"] == "cv_progress_bridge", st
    ing = c.post(f"/projects/{pid}/cv-progress/ingest",
                 json={"activity": "A1", "percent": 65, "source": "vision-svc"}).json()
    assert ing["accepted"] is False, ing                                 # nothing fabricated when disabled

    # --- PERF-4: name→id resolution is a single SQL probe (find_id_by_field), same answers as the
    # old per-estimate Python scan: case-insensitive name hit, id passthrough, miss → not applied.
    act = c.post(f"/projects/{pid}/modules/schedule_activity",
                 json={"data": {"name": "Frame L2", "start": "2026-03-01",
                                "finish": "2026-03-10"}}).json()["id"]
    os.environ["AEC_CV_BRIDGE"] = "1"
    by_name = c.post(f"/projects/{pid}/cv-progress/ingest",
                     json={"activity": "  frame l2 ", "percent": 40}).json()
    assert by_name["applied"] is True and by_name["activity_id"] == act, by_name
    got = c.get(f"/projects/{pid}/modules/schedule_activity/{act}").json()
    assert float(got["data"]["percent"]) == 40.0, got["data"]
    by_id = c.post(f"/projects/{pid}/cv-progress/ingest",
                   json={"activity": act, "percent": 55}).json()
    assert by_id["applied"] is True and by_id["activity_id"] == act, by_id
    miss = c.post(f"/projects/{pid}/cv-progress/ingest",
                  json={"activity": "No Such Task", "percent": 10}).json()
    assert miss.get("applied") is False and "no schedule_activity matched" in miss["apply_error"], miss
    os.environ.pop("AEC_CV_BRIDGE", None)

# --- E2 engine: when the operator enables the flag, estimates are accepted (clamped) --------------
os.environ["AEC_CV_BRIDGE"] = "1"
assert cv_bridge.enabled() is True
acc = cv_bridge.ingest({"activity": "A1", "percent": 140, "source": "vision-svc"})
assert acc["accepted"] is True and acc["percent"] == 100.0, acc          # clamped to 0–100
os.environ.pop("AEC_CV_BRIDGE", None)

# --- CV-BRIDGE-DARK: `accepted` is a verdict about the PAYLOAD, not about the writes -------------
# The batch door has reported per-item outcomes since the write path landed; the SUMMARY reported
# only `accepted`, which is decided before the first write is attempted and therefore stays True on
# a sweep in which every one of them failed.
os.environ["AEC_CV_BRIDGE"] = "1"

# ① the single door now ANSWERS the did-it-land question when no activity was given. It used to
# return `accepted: true` with NO `applied` key, and a missing key is `undefined`, not `false`.
_bare = cv_bridge.ingest({"percent": 30})
assert _bare["accepted"] is True and "NOT written" in _bare["note"], _bare
assert "written to that activity" in cv_bridge.ingest({"activity": "A1", "percent": 30})["note"]

# ② the batch cap is a REFUSAL, not a truncation: applying 500 of a 5,000-estimate sweep and
# reporting success is the defect `write_coverage` exists to prevent, at the door.
_over = cv_bridge.ingest_batch([{"activity": "A", "percent": 1}] * (cv_bridge.MAX_BATCH + 1))
assert _over["accepted"] is False and _over["limit"] == cv_bridge.MAX_BATCH, _over
assert str(cv_bridge.MAX_BATCH) in _over["reason"] and "split" in _over["reason"], _over
assert cv_bridge.ingest_batch([{"activity": "A", "percent": 1}] * cv_bridge.MAX_BATCH)["accepted"]
os.environ.pop("AEC_CV_BRIDGE", None)

# ③ the four reasons a percent did not move, each counted separately — `written` is the only one
# that means a `schedule_activity.percent` changed.
_cov = cv_bridge.write_coverage([
    {"ok": True, "activity": "A", "applied": True},
    {"ok": True, "activity": "B", "applied": False, "apply_error": "no schedule_activity matched"},
    {"ok": True, "activity": "", "applied": False, "apply_error": "no activity given"},
    {"ok": False, "reason": "percent must be a number 0–100"},
])
assert _cov == {"received": 4, "written": 1, "write_failed": 1, "no_activity": 1, "invalid": 1,
                "reason": "1 of 4 estimate(s) were written"}, _cov
assert "complete" not in _cov, _cov      # no boolean, and no null placeholder to be read as one

# ④ EVERY-OF-NOTHING IS NOT "EVERY". `len(written) == len(items)` holds on an empty batch, so a
# reason computed in the obvious order says "every estimate was written" about zero estimates —
# the vacuous-quantifier shape `services/api/test_quant_vacuous.py` exists for. Asserted rather
# than described, because the guard is one line and reordering it is invisible in a diff.
assert cv_bridge.write_coverage([])["reason"] == "the batch was empty, so nothing was written"
assert cv_bridge.write_coverage([{"ok": True, "activity": "A", "applied": True}])["reason"] \
    == "every estimate in the batch was written"
assert cv_bridge.write_coverage([{"ok": True, "activity": "A", "applied": False}])["reason"] \
    == "nothing was written"

print("FIELD AI OK - E1: productivity log -> units/man-hr per entry + by-trade rollup (Concrete "
      "210 cy / 96 mh = 2.188 cy/man-hr; no-production entry excluded); report PDF served. E2: CV "
      "bridge disabled by default (ingest = no-op, nothing fabricated); enabling AEC_CV_BRIDGE accepts "
      "estimates, clamped 0–100. CV-BRIDGE-DARK: the batch summary states how much of a sweep was "
      f"WRITTEN rather than only that it was accepted, the cap ({cv_bridge.MAX_BATCH}) refuses "
      "instead of truncating, and every-of-nothing is not 'every'")
