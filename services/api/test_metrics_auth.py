"""Opt-in /metrics authentication (SEC F2): /metrics is open by default (existing scrapers unaffected),
but when AEC_METRICS_AUTH=1 it requires the AEC_API_KEY bearer. The flag is read per-request, so this
one process exercises both modes by toggling os.environ.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_metrics_auth.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_metrics_auth.db"
os.environ["STORAGE_DIR"] = "./test_storage_metrics_auth"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_METRICS_AUTH", None)      # default posture: open
os.environ["AEC_API_KEY"] = "scrape-secret"   # the bearer that will be required when the gate is on
for _f in ("./test_metrics_auth.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api.main import app                # noqa: E402

BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

with TestClient(app) as c:
    # --- default (flag unset): /metrics is open, no bearer needed -------------------------------
    os.environ.pop("AEC_METRICS_AUTH", None)
    r = c.get("/metrics")
    assert r.status_code == 200, r.status_code
    assert "text/plain" in r.headers.get("content-type", ""), r.headers.get("content-type")
    assert "process_uptime_seconds" in r.text, r.text[:200]

    # --- opt-in (AEC_METRICS_AUTH=1): the bearer is required ------------------------------------
    os.environ["AEC_METRICS_AUTH"] = "1"
    # no bearer → 401
    assert c.get("/metrics").status_code == 401, "expected 401 without bearer when gate on"
    # wrong bearer → 401
    assert c.get("/metrics", headers=BEARER("nope")).status_code == 401, "expected 401 with wrong bearer"
    # wrong bearer of the SAME length → 401 (exercises the constant-time hmac.compare_digest path)
    assert c.get("/metrics", headers=BEARER("xcrape-secret")).status_code == 401, "expected 401 with same-length wrong bearer"
    # correct bearer → 200 and still Prometheus text
    ok = c.get("/metrics", headers=BEARER("scrape-secret"))
    assert ok.status_code == 200, ok.status_code
    assert "process_uptime_seconds" in ok.text, ok.text[:200]

    # --- toggling back off restores open access (no restart) ------------------------------------
    os.environ.pop("AEC_METRICS_AUTH", None)
    assert c.get("/metrics").status_code == 200, "expected open again after clearing the flag"

print("METRICS AUTH OK - /metrics open by default; AEC_METRICS_AUTH=1 requires AEC_API_KEY bearer "
      "(401 without/wrong, 200 with); toggle is live per-request")
