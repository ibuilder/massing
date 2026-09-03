"""Observability: the Prometheus /metrics endpoint exposes request counts, latency summary, in-flight
gauge and uptime in the 0.0.4 text format, and counters increment as requests are served.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_metrics.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_metrics.db"
os.environ["STORAGE_DIR"] = "./test_storage_metrics"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_metrics.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _count(text: str, needle: str) -> int:
    for line in text.splitlines():
        if line.startswith(needle):
            try:
                return int(float(line.rsplit(" ", 1)[1]))
            except (ValueError, IndexError):
                return 0
    return 0


with TestClient(app) as c:
    # generate some traffic on a stable route template
    c.post("/projects", json={"name": "Metrics"})
    for _ in range(3):
        c.get("/health")

    r = c.get("/metrics")
    assert r.status_code == 200, r.status_code
    body = r.text
    # content type is Prometheus text exposition
    assert "text/plain" in r.headers.get("content-type", ""), r.headers.get("content-type")
    # the three metric families + HELP/TYPE headers are present
    for needle in ("# TYPE http_requests_total counter",
                   "# TYPE http_request_duration_seconds summary",
                   "# TYPE http_requests_in_flight gauge",
                   "process_uptime_seconds"):
        assert needle in body, needle
    # health was served at least 3 times and is counted (route template, not raw path)
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in body, body[:500]
    health_n = _count(body, 'http_requests_total{method="GET",route="/health",status="200"}')
    assert health_n >= 3, health_n
    # a follow-up request increments the counter
    c.get("/health")
    body2 = c.get("/metrics").text
    assert _count(body2, 'http_requests_total{method="GET",route="/health",status="200"}') > health_n

print("METRICS OK - /metrics serves Prometheus text (requests_total + duration summary + in-flight + "
      "uptime); /health counted by route template and increments across requests")
