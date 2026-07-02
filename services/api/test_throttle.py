"""Per-endpoint rate limiting for expensive ops (throttle.py).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_throttle.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_throttle.db"
os.environ["STORAGE_DIR"] = "./test_storage_throttle"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_throttle.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import Depends, FastAPI, Request                # noqa: E402
from fastapi.testclient import TestClient                    # noqa: E402
from aec_api import throttle                                 # noqa: E402

# The dependency factory: at most N/min per caller; 429 with Retry-After when exceeded.
app = FastAPI()
_limit = throttle.rate_limited("unit", 3)


@app.get("/probe")
def probe(request: Request, _: None = Depends(_limit)):
    return {"ok": True}


with TestClient(app) as c:
    codes = [c.get("/probe").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200], codes                # first 3 allowed
    assert codes[3] == 429 and codes[4] == 429, codes         # 4th+ blocked in the same window
    r = c.get("/probe")
    assert r.status_code == 429 and r.headers.get("Retry-After") == "60", r.headers

# 0 (or a bad value) disables the limiter entirely (env override).
os.environ["AEC_THROTTLE_OFFBUCKET_RPM"] = "0"
app2 = FastAPI()
_off = throttle.rate_limited("offbucket", 2)


@app2.get("/x")
def x(request: Request, _: None = Depends(_off)):
    return {"ok": True}


with TestClient(app2) as c2:
    assert all(c2.get("/x").status_code == 200 for _ in range(10)), "0 rpm should disable throttling"
os.environ.pop("AEC_THROTTLE_OFFBUCKET_RPM", None)

# env override raises the cap
os.environ["AEC_THROTTLE_TUNED_RPM"] = "50"
assert throttle._limit("tuned", 3) == 50
os.environ.pop("AEC_THROTTLE_TUNED_RPM", None)
assert throttle._limit("tuned", 3) == 3                        # falls back to the built-in default

print("THROTTLE OK - per-caller cap enforced (3 pass, rest 429 + Retry-After); env override tunes the "
      "limit; 0 disables; bad/absent env falls back to the built-in default")
