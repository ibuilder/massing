"""E57 point-cloud import — optional `pye57` dependency gating + the convert endpoint.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_e57.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_e57.db"
os.environ["STORAGE_DIR"] = "./test_storage_e57"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_e57.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import e57  # noqa: E402
from aec_api.main import app  # noqa: E402

st = e57.status()
assert set(st) == {"available", "max_points", "message"}, st
assert isinstance(st["available"], bool) and st["max_points"] == 2_000_000, st

with TestClient(app) as c:
    r = c.get("/convert/e57/status")
    assert r.status_code == 200 and r.json()["available"] == st["available"], r.text

    # post a (bogus) .e57 through the generic /convert dispatcher
    files = {"file": ("scan.e57", b"NOT-A-REAL-E57", "application/octet-stream")}
    resp = c.post("/convert", files=files)
    if st["available"]:
        # pye57 present → it should fail to parse our bogus bytes (422), not 503/500
        assert resp.status_code == 422, ("expected parse error", resp.status_code, resp.text[:160])
    else:
        # pye57 absent → actionable 503 telling the operator to install it
        assert resp.status_code == 503 and "pye57" in resp.text, (resp.status_code, resp.text[:160])
        try:
            e57.convert_to_xyz(b"x")
            raise AssertionError("convert_to_xyz should raise when pye57 is unavailable")
        except RuntimeError as exc:
            assert "pye57" in str(exc), exc

print(f"E57 OK - status gating ({'available' if st['available'] else 'needs pye57'}); "
      "convert endpoint returns the right actionable status; engine raises cleanly when unavailable")
