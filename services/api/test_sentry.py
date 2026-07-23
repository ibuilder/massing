"""Sentry-compatible error alerting: env-gated no-op, handled-500 capture, fail-open, PII scrubbing.
Uses a fake sentry_sdk injected into sys.modules so nothing touches the network.
Run: PYTHONPATH=src:../data/src python3 test_sentry.py"""
import os
import sys
import types

os.environ["DATABASE_URL"] = "sqlite:///./test_sentry.db"
os.environ["STORAGE_DIR"] = "./test_storage_sentry"
os.environ["AEC_LOCAL_MODE"] = "1"          # single-operator mode → no IdP needed in tests
os.environ.pop("AEC_RBAC", None)
for _k in ("AEC_SENTRY_DSN", "SENTRY_DSN"):  # start from a known DSN-unset state
    os.environ.pop(_k, None)
for _f in ("./test_sentry.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import sentry  # noqa: E402
from aec_api.main import app  # noqa: E402


# --- a fake sentry_sdk so init()/capture_exception() never hit the network -----------------------
class _FakeSentry:
    def __init__(self):
        self.init_kwargs = None
        self.init_calls = 0
        self.captured = []
        self.tags = {}
        self.raise_on_capture = False

    def init(self, **kw):
        self.init_calls += 1
        self.init_kwargs = kw

    def capture_exception(self, exc):
        if self.raise_on_capture:
            raise RuntimeError("sentry transport down")
        self.captured.append(exc)

    def set_tag(self, k, v):
        self.tags[k] = v


def _install_fake_sentry() -> _FakeSentry:
    fake = _FakeSentry()
    mod = types.ModuleType("sentry_sdk")
    mod.init = fake.init
    mod.capture_exception = fake.capture_exception
    mod.set_tag = fake.set_tag
    integ = types.ModuleType("sentry_sdk.integrations")
    fastapi_mod = types.ModuleType("sentry_sdk.integrations.fastapi")
    starlette_mod = types.ModuleType("sentry_sdk.integrations.starlette")

    class FastApiIntegration:  # noqa: D401 — stand-in for the real integration class
        pass

    class StarletteIntegration:
        pass

    fastapi_mod.FastApiIntegration = FastApiIntegration
    starlette_mod.StarletteIntegration = StarletteIntegration
    integ.fastapi = fastapi_mod
    integ.starlette = starlette_mod
    mod.integrations = integ
    sys.modules.update({
        "sentry_sdk": mod,
        "sentry_sdk.integrations": integ,
        "sentry_sdk.integrations.fastapi": fastapi_mod,
        "sentry_sdk.integrations.starlette": starlette_mod,
    })
    return fake


# a route that always 500s, so the global exception handler runs
app.add_api_route("/__sentry_boom__",
                  lambda: (_ for _ in ()).throw(RuntimeError("boom-sentry")), methods=["GET"])


# --- 1. DSN UNSET → no-op: app boots, 500 path unchanged, SDK never touched ----------------------
sentry._ENABLED = False
fake = _install_fake_sentry()
assert sentry.init() is False, "init() with no DSN returns False"
assert sentry.enabled() is False and fake.init_calls == 0, "no DSN → SDK never initialized"
with TestClient(app, raise_server_exceptions=False) as c:
    r = c.get("/__sentry_boom__")
    assert r.status_code == 500 and r.json().get("request_id"), r.text[:200]
    assert r.headers.get("X-Request-ID") == r.json()["request_id"], r.headers
assert fake.captured == [], "DSN unset → capture_exception NOT called"
print("1. DSN unset: app boots, 500 unchanged, capture_exception not called")


# --- 2. DSN SET → init runs with safe options; handled 500 is captured + request-id tagged --------
os.environ["AEC_SENTRY_DSN"] = "https://pub@example.ingest.glitchtip.test/1"
os.environ["AEC_SENTRY_ENVIRONMENT"] = "staging"
fake = _install_fake_sentry()
with TestClient(app, raise_server_exceptions=False) as c:   # lifespan runs sentry.init()
    assert sentry.enabled() is True and fake.init_calls == 1, "DSN set → init ran once"
    kw = fake.init_kwargs
    assert kw["send_default_pii"] is False, kw
    assert kw["traces_sample_rate"] == 0.0, "error reporting only (no tracing)"
    assert kw["environment"] == "staging", kw
    assert callable(kw["before_send"]), "before_send installed"
    assert len(kw["integrations"]) == 2, "explicit FastAPI + Starlette integrations"
    r = c.get("/__sentry_boom__")
    assert r.status_code == 500 and r.json().get("request_id"), r.text[:200]
    rid = r.json()["request_id"]
assert len(fake.captured) == 1 and isinstance(fake.captured[0], RuntimeError), fake.captured
assert fake.tags.get("request_id") == rid, ("event tagged with request-id", fake.tags, rid)
print(f"2. DSN set: init ran (env=staging, pii off, traces=0), captured 1 exc, tagged rid={rid}")


# --- 3. capture failure → fail-open: the normal 500 response is unaffected ------------------------
fake = _install_fake_sentry()
fake.raise_on_capture = True
with TestClient(app, raise_server_exceptions=False) as c:
    assert sentry.enabled() is True
    r = c.get("/__sentry_boom__")
    assert r.status_code == 500 and r.json().get("request_id"), "capture blew up but 500 is clean"
print("3. capture failure: swallowed, 500 response unaffected (fail-open)")


# --- 4. PII scrubbing: before_send drops auth/cookie/x-api-key headers + body --------------------
event = {"request": {
    "headers": {"Authorization": "Bearer secret-token", "Cookie": "aec_token=abc",
                "X-Api-Key": "k-123", "User-Agent": "pytest"},
    "data": {"password": "hunter2"},
}}
scrubbed = sentry._before_send(event, None)
hdrs = scrubbed["request"]["headers"]
assert hdrs["Authorization"] == "[scrubbed]" and hdrs["Cookie"] == "[scrubbed]", hdrs
assert hdrs["X-Api-Key"] == "[scrubbed]", hdrs
assert hdrs["User-Agent"] == "pytest", "non-sensitive headers preserved"
assert scrubbed["request"]["data"] == "[scrubbed]", "credential-bearing body dropped"
print("4. PII scrubbing: authorization/cookie/x-api-key + body scrubbed, others preserved")

# cleanup env so import side effects don't leak to other test modules
for _k in ("AEC_SENTRY_DSN", "AEC_SENTRY_ENVIRONMENT"):
    os.environ.pop(_k, None)
sentry._ENABLED = False
print("test_sentry OK")
