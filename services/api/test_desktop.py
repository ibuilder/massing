"""Single-process desktop runtime: API + SPA from one origin, SQLite + local mode.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_desktop.py"""
import os
from pathlib import Path

# point at the built web app (repo dist) before importing the app
DIST = Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"
os.environ["DATABASE_URL"] = "sqlite:///./desktop_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_desktop"
os.environ["AEC_LOCAL_MODE"] = "1"
os.environ["AEC_AUTOSYNC"] = "0"
if DIST.is_dir():
    os.environ["AEC_WEB_DIST"] = str(DIST)
for f in ("./desktop_test.db",):
    if os.path.exists(f):
        os.remove(f)

# the desktop module's data-dir/web-dist helpers resolve sensibly
from aec_api import desktop  # noqa: E402
assert desktop.data_dir().exists()

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    # API still answers at root (explicit routes win over the SPA catch-all mount)
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/capabilities").json()["local_mode"] is True
    assert isinstance(c.get("/projects").json(), list)            # SQLite db works, no login

    if DIST.is_dir():
        # the SPA is served from the same origin, cross-origin isolated for web-ifc WASM
        r = c.get("/")
        assert r.status_code == 200 and "text/html" in r.headers["content-type"], r.status_code
        assert r.headers.get("cross-origin-opener-policy") == "same-origin", dict(r.headers)
        assert r.headers.get("cross-origin-embedder-policy") == "require-corp", dict(r.headers)
        assert "<title" in r.text.lower(), r.text[:200]
        print("DESKTOP OK - one process serves API (root) + SPA (/) with COOP/COEP, SQLite, local mode")
    else:
        print("DESKTOP OK - API + SQLite + local mode (web dist not built; SPA serving skipped)")
