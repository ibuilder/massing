"""Auto-propagate 2D on model change: publishing a new model bumps an in-process version that the 2D
sync-status surfaces (and /drawings/stream pushes), so on-demand drawings regenerate. No event bus.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_model_events.py"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_model_events.db"
os.environ["STORAGE_DIR"] = "./test_storage_model_events"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_model_events.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import model_events  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- unit: monotonic version + signature-reconcile ------------------------------------------------
assert model_events.current("px")["version"] == 0
assert model_events.bump("px", "sigA")["version"] == 1
assert model_events.bump("px", "sigB")["version"] == 2
# observe with an unchanged signature does NOT bump; a changed one does
assert model_events.observe("px", "sigB")["version"] == 2
assert model_events.observe("px", "sigC")["version"] == 3


# Redis fail-open: a broken client must never break publishing/reads — falls back to in-process.
class _BrokenRedis:
    def pipeline(self, *a, **k):
        raise RuntimeError("redis down")

    def hgetall(self, *a, **k):
        raise RuntimeError("redis down")


_saved_redis = model_events._redis
model_events._redis = _BrokenRedis()
assert model_events.bump("fo", "s1")["version"] == 1, "bump must fall back to in-process on Redis error"
assert model_events.current("fo")["version"] == 1, "current must fall back to in-process on Redis error"


# Redis SHARED path: a fake implementing the redis hash/pipeline contract proves the version is shared
# (any worker's bump is visible to any worker's current) and stays monotonic — the multi-worker semantics.
class _FakeRedis:
    def __init__(self):
        self.store: dict[str, dict[str, str]] = {}

    def pipeline(self, transaction=True):
        outer = self

        class _P:
            def __init__(self):
                self.results = []

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def hincrby(self, key, field, n):
                h = outer.store.setdefault(key, {})
                h[field] = str(int(h.get(field, 0)) + n)
                self.results.append(int(h[field]))

            def hset(self, key, mapping=None):
                h = outer.store.setdefault(key, {})
                for k, v in (mapping or {}).items():
                    h[k] = str(v)
                self.results.append(1)

            def execute(self):
                return self.results

        return _P()

    def hgetall(self, key):
        return dict(self.store.get(key, {}))


fake = _FakeRedis()
model_events._redis = fake
b1 = model_events.bump("shared", "sA")
assert b1["version"] == 1 and b1["signature"] == "sA", b1
# a "different worker" reads the same shared store and sees the bump
assert model_events.current("shared") == {"version": 1, "signature": "sA", "at": b1["at"]}, \
    model_events.current("shared")
assert model_events.bump("shared", "sB")["version"] == 2, "shared version must increment across bumps"
assert model_events.current("shared")["version"] == 2 and model_events.current("shared")["signature"] == "sB"
# observe reconciles against the shared signature (no bump when unchanged; bump when changed)
assert model_events.observe("shared", "sB")["version"] == 2
assert model_events.observe("shared", "sC")["version"] == 3
model_events._redis = _saved_redis


def _props(guids):
    return {"schema": "IFC4", "elements": [{"guid": g, "ifc_class": "IfcWall"} for g in guids]}


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    # no model yet -> version 0, not stale-able
    s0 = c.get(f"/projects/{pid}/drawings/sync-status").json()
    assert s0["version"] == 0 and s0["model_loaded"] is False, s0

    # publish a model -> version bumps to 1, signature appears
    c.post(f"/projects/{pid}/properties/index",
           files={"file": ("props.json", json.dumps(_props(["g1", "g2"])).encode(), "application/json")})
    s1 = c.get(f"/projects/{pid}/drawings/sync-status").json()
    assert s1["version"] == 1 and s1["model_loaded"] and s1["signature"], s1

    # re-reading sync-status with the SAME model must NOT keep bumping (idempotent)
    assert c.get(f"/projects/{pid}/drawings/sync-status").json()["version"] == 1

    # publish a CHANGED model -> version bumps again + signature changes (2D is now stale)
    c.post(f"/projects/{pid}/properties/index",
           files={"file": ("props.json", json.dumps(_props(["g1", "g2", "g3"])).encode(), "application/json")})
    s2 = c.get(f"/projects/{pid}/drawings/sync-status").json()
    assert s2["version"] == 2 and s2["signature"] != s1["signature"], (s1, s2)

print("MODEL EVENTS OK - monotonic version + signature-reconcile (no double-bump on unchanged); "
      "publishing a model bumps sync-status version (0->1), a re-read is idempotent (stays 1), and a "
      "changed model bumps again (->2) with a new signature - the auto-propagate staleness signal")
