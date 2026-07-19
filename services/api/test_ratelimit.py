"""Per-IP rate limiter (first-layer DoS guard). Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ratelimit.py

The limiter reads AEC_RATE_LIMIT_RPM at import, so set it BEFORE importing the app. No AEC_REDIS_URL
here, so this exercises the in-process path; the Redis path runs through the same middleware with a
shared atomic counter (fail-open to this same in-process logic on any Redis error)."""
import os

os.environ["AEC_RATE_LIMIT_RPM"] = "5"          # tiny limit so the test is fast
os.environ["DATABASE_URL"] = "sqlite:///./_rl_test.db"
os.environ.pop("AEC_REDIS_URL", None)           # force the in-process path
for f in ("./_rl_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    # /health and /metrics are exempt — hammering them never trips the limit
    for _ in range(20):
        assert c.get("/health").status_code == 200
    assert c.get("/metrics").status_code == 200

    # the limiter buckets per wall-clock minute — if the boundary falls inside the 7-request loop the
    # count resets mid-loop and every request legally passes (seen as a 1-in-60 flake under a loaded
    # parallel suite). Start the loop clear of the rollover.
    import time
    from datetime import datetime
    if datetime.now().second >= 45:
        time.sleep(61 - datetime.now().second)

    # a limited route: first 5 in the window pass, the 6th+ is 429 with Retry-After
    codes = [c.get("/projects").status_code for _ in range(7)]
    assert codes[:5] == [200, 200, 200, 200, 200], codes
    assert codes[5] == 429 and codes[6] == 429, codes
    r = c.get("/projects")
    assert r.status_code == 429 and r.headers.get("Retry-After") == "60", (r.status_code, r.headers)
    assert "rate limit" in r.json()["detail"], r.text

print("RATELIMIT OK - health/metrics exempt; 5 rpm enforced (6th -> 429 + Retry-After); in-process "
      "path (Redis shares the same middleware via atomic INCR, fail-open)")

if os.path.exists("./_rl_test.db"):
    try:
        os.remove("./_rl_test.db")
    except OSError:
        pass
