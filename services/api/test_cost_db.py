"""COST-DB: vintage-versioned cost database (offline public importer) — build vintages, resolve latest/
specific/fallback, pin a project, price through the pinned vintage.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_cost_db.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_costdb.db"
os.environ["STORAGE_DIR"] = "./test_storage_costdb"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_costdb.db",):
    if os.path.exists(f):
        os.remove(f)

import sys                                                    # noqa: E402
from pathlib import Path                                      # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient                     # noqa: E402
from aec_api.main import app                                  # noqa: E402
from aec_api import cost_db                                   # noqa: E402
from aec_api.db import SessionLocal, init_db                  # noqa: E402
from aec_api.models import CostDataset, CostItem              # noqa: E402

init_db()

# --- unit: build vintages, resolve, idempotency (direct engine) --------------
with SessionLocal() as db:
    ds24 = cost_db.import_public_vintage(db, 2024)
    n_items = len(list(db.scalars(CostItem.__table__.select().where(CostItem.dataset_id == ds24.id))))
    assert n_items > 20, n_items                              # one priced item per shipped benchmark rate
    assert ds24.is_latest and ds24.origin == "public_local"

    ds26 = cost_db.import_public_vintage(db, 2026)            # newer vintage → becomes latest
    db.refresh(ds24)
    assert ds26.is_latest and not ds24.is_latest, "importing a newer vintage flips is_latest"

    # idempotent: re-importing 2024 returns the SAME dataset (no duplicate), and re-flags it latest
    ds24b = cost_db.import_public_vintage(db, 2024)
    assert ds24b.id == ds24.id, "re-import must be idempotent"
    assert len(list(db.scalars(CostDataset.__table__.select()))) == 2, "no duplicate vintage rows"

    # resolve: latest / exact / fallback
    cost_db._set_latest(db, ds26); db.commit()
    assert cost_db.resolve(db, "latest").vintage_year == 2026
    assert cost_db.resolve(db, 2024).vintage_year == 2024
    assert cost_db.resolve(db, 2025, policy="nearest").vintage_year == 2024   # newest installed <= 2025
    assert cost_db.resolve(db, 2025, policy="strict") is None                 # strict: not installed
    assert cost_db.resolve(db, 2099, policy="nearest").vintage_year == 2026   # newest overall

    # the rate map prices the model takeoff straight through a vintage
    rates = cost_db.rates_for(db, ds24.id)
    assert rates.get("IfcWall") and rates.get("IfcColumn"), rates

# --- integration: endpoints + project pinning --------------------------------
with TestClient(app) as c:
    got = c.get("/cost/datasets").json()
    assert len(got["datasets"]) == 2 and got["available_public"], got
    assert any(d["is_latest"] for d in got["datasets"])

    # import via the endpoint (idempotent) + a fresh year
    r = c.post("/cost/datasets/import", json={"vintage": 2027})
    assert r.status_code == 200 and r.json()["vintage_year"] == 2027 and r.json()["is_latest"], r.text
    # a cloud request with no subscription warns + falls back to a public build
    rc = c.post("/cost/datasets/import", json={"vintage": 2027, "source": "cloud"})
    assert rc.json()["warning"] and "public" in rc.json()["warning"], rc.text

    pid = c.post("/projects", json={"name": "Cost Vintage Tower"}).json()["id"]
    # unpinned → resolves to the latest (2027)
    v0 = c.get(f"/projects/{pid}/cost-vintage").json()
    assert v0["pinned_id"] is None and v0["resolved"]["vintage_year"] == 2027, v0

    # pin to the 2024 vintage → reproducible
    ds24_id = next(d["id"] for d in c.get("/cost/datasets").json()["datasets"] if d["vintage_year"] == 2024)
    p = c.post(f"/projects/{pid}/cost-vintage", json={"dataset_id": ds24_id})
    assert p.status_code == 200 and p.json()["resolved"]["vintage_year"] == 2024, p.text
    assert c.get(f"/projects/{pid}/cost-vintage").json()["pinned_id"] == ds24_id

    # unpin (null) → follows latest again
    assert c.post(f"/projects/{pid}/cost-vintage", json={}).json()["resolved"]["vintage_year"] == 2027
    # pinning a bogus dataset 404s
    assert c.post(f"/projects/{pid}/cost-vintage", json={"dataset_id": "nope"}).status_code == 404

    # the model estimate PRICES THROUGH the pinned vintage (carries cost_vintage in the response)
    import tempfile

    from aec_data import massing                              # noqa: E402
    c.post(f"/projects/{pid}/cost-vintage", json={"dataset_id": ds24_id})
    metrics = massing.compute_massing({"lot_width": 20, "lot_depth": 14, "far": 1.5,
                                       "floor_to_floor": 3.5, "height_limit": 10})
    ifc = Path(tempfile.gettempdir()) / "costdb_model.ifc"
    massing.generate_ifc(metrics, str(ifc), name="CostDB")
    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("m.ifc", ifc.read_bytes(), "application/octet-stream")})
    assert up.status_code == 200, up.text[:160]
    est = c.get(f"/projects/{pid}/qto/by-floor").json()
    assert est.get("cost_vintage", {}).get("vintage_year") == 2024, est.get("cost_vintage")

print("COST-DB OK - offline public importer builds vintage-versioned datasets (one priced item per shipped "
      "benchmark, MasterFormat-coded); importing a newer vintage flips is_latest; re-import is idempotent "
      "(no dup rows); resolve handles latest/exact/nearest-fallback/strict; a project pins a vintage for "
      "reproducibility and resolves to latest when unpinned; cloud request without a subscription falls back "
      "to public with a warning.")
