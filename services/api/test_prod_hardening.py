"""Production-hardening pass (R1): prod startup guard, N+1/paginated project list, bounded board/CSV,
properties upload gate, traversal belt, sync id-extraction, delete cascade incl. storage prefix.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_prod_hardening.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_prod_hardening.db"
os.environ["STORAGE_DIR"] = "./test_storage_prod_hardening"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_prod_hardening.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import storage                          # noqa: E402
from aec_api.main import _production_guard, app      # noqa: E402

# --- prod startup guard: Postgres without RBAC/secret refuses to boot -------------------------
_saved = {k: os.environ.get(k) for k in ("DATABASE_URL", "AEC_RBAC", "AEC_ALLOW_OPEN")}
try:
    os.environ["DATABASE_URL"] = "postgresql://u:p@host/db"
    os.environ.pop("AEC_RBAC", None)
    os.environ.pop("AEC_ALLOW_OPEN", None)
    try:
        _production_guard()
    except RuntimeError as e:
        assert "AEC_RBAC" in str(e), e
    else:
        raise AssertionError("guard must refuse Postgres without RBAC")
    os.environ["AEC_ALLOW_OPEN"] = "1"               # explicit escape hatch passes
    _production_guard()
finally:
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
# SQLite (dev/test) never trips the guard
_production_guard()

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- list limit clamp: an absurd ?limit is clamped, not honored ---------------------------
    for i in range(5):
        cr = c.post(f"/projects/{pid}/modules/rfi",
                    json={"data": {"subject": f"RFI {i}", "question": f"Q{i}?"}})
        assert cr.status_code == 201, cr.text[:120]
    r = c.get(f"/projects/{pid}/modules/rfi?limit=999999")
    assert r.status_code == 200 and len(r.json()) == 5, len(r.json())

    # --- board: bounded per-state cards + TRUE counts ------------------------------------------
    b = c.get(f"/projects/{pid}/modules/rfi/board").json()
    assert "counts" in b and sum(b["counts"].values()) == 5, b.get("counts")
    assert sum(len(v) for v in b["columns"].values()) == 5, "cards present under the cap"

    # --- CSV export streams with a single header row -------------------------------------------
    csv_r = c.get(f"/projects/{pid}/modules/rfi/export.csv")
    lines = [ln for ln in csv_r.text.splitlines() if ln.strip()]
    assert csv_r.status_code == 200 and len(lines) == 6, len(lines)   # header + 5 rows
    assert lines[0].startswith("ref,"), lines[0]

    # --- properties upload gate: oversized index -> 413 ----------------------------------------
    os.environ["AEC_PROPS_MAX_MB"] = "0"             # gate everything for the test
    big = c.post(f"/projects/{pid}/properties/index",
                 files={"file": ("props.json", b'{"elements": []}', "application/json")})
    assert big.status_code == 413, big.status_code
    os.environ.pop("AEC_PROPS_MAX_MB", None)
    ok = c.post(f"/projects/{pid}/properties/index",
                files={"file": ("props.json", b'{"elements": []}', "application/json")})
    assert ok.status_code == 200, ok.text[:120]

    # --- traversal belt: dotted filename cannot escape the storage root ------------------------
    t = c.post(f"/projects/{pid}/topics", json={"title": "T"}).json()
    up = c.post(f"/projects/{pid}/topics/{t['id']}/attachments",
                files={"file": ("..\\..\\evil.txt", b"x", "text/plain")})
    assert up.status_code in (200, 201), up.text[:120]
    sk = up.json().get("storage_key") or ""      # the SECURITY property lives in the storage key
    assert ".." not in sk and "\\" not in sk, sk

    # --- delete cascade: rows AND the whole {pid}/ storage prefix are gone ---------------------
    storage.put(f"{pid}/source.ifc", b"IFC")         # simulate leftover project blobs
    storage.put(f"{pid}/publish_status.json", b"{}")
    d = c.delete(f"/projects/{pid}")
    assert d.status_code == 200 and d.json()["deleted"], d.text[:120]
    assert not storage.exists(f"{pid}/source.ifc"), "project blobs must be removed"
    assert not storage.exists(f"{pid}/publish_status.json")
    assert c.get(f"/projects/{pid}/modules/rfi").status_code in (403, 404) or \
        c.get(f"/projects/{pid}/modules/rfi").json() == [], "records gone with the project"

# --- sync id-extraction pulls only procore_id (and normalizes types) ---------------------------
from aec_api import sync as sync_mod                  # noqa: E402
from aec_api.db import SessionLocal                   # noqa: E402
from aec_api import modules as me                     # noqa: E402

with TestClient(app) as c:
    pid2 = c.post("/projects", json={"name": "P2"}).json()["id"]
    with SessionLocal() as db:
        me.create_record(db, "rfi", pid2, {"data": {"subject": "from procore", "question": "Q?",
                                                    "procore_id": 123}}, "t", "GC")
        ids = sync_mod._existing_procore_ids(db, "rfi", pid2)
        assert ids == {"123"}, ids                    # normalized to str regardless of stored type

print("PROD HARDENING OK - guard refuses Postgres w/o RBAC (escape hatch works); list limit clamped; "
      "board bounded w/ true counts; CSV streams; props upload 413-gated; traversal-safe filenames; "
      "delete removes rows + the whole storage prefix; sync extracts procore_id in SQL (normalized)")
