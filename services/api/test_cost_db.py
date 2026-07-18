"""COST-DB: vintage-versioned cost database (offline public importer) — build vintages, resolve latest/
specific/fallback, pin a project, price through the pinned vintage.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_cost_db.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_costdb.db"
os.environ["STORAGE_DIR"] = "./test_storage_costdb"
os.environ["IFC_DIR"] = "./test_ifc_costdb"   # writable; default /app/ifc is read-only in the CI container
os.environ.pop("AEC_RBAC", None)
for f in ("./test_costdb.db",):
    if os.path.exists(f):
        os.remove(f)

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import cost_db  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import CostDataset, CostItem  # noqa: E402

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

    # COST-DB localization + escalation: a project pinned to the 2024 vintage, priced for a North
    # America region and a 2034 target year, gets its national-average rates multiplied by the region
    # location index AND escalated from 2024 → 2034 at the region rate.
    from aec_api import market_intelligence as mi  # noqa: E402
    from aec_api.models import Project  # noqa: E402
    proj = Project(name="Loc/Esc"); proj.cost_dataset_id = ds24.id
    db.add(proj); db.commit()
    adj_rates, meta = cost_db.rates_for_project(db, proj, region="north_america", to_year=2034)
    loc = mi.region_data("north_america")["location_index"]     # 1.05
    esc = (1 + mi.region_data("north_america")["escalation_pct"] / 100.0) ** (2034 - 2024)
    assert meta["location_index"] == round(loc, 4) and meta["vintage_year"] == 2024, meta
    assert abs(meta["combined_factor"] - round(loc * esc, 4)) < 1e-6, meta
    assert adj_rates["IfcWall"] == round(rates["IfcWall"] * loc * esc, 2), (adj_rates["IfcWall"], meta)
    assert adj_rates["IfcWall"] > rates["IfcWall"], "localized+escalated must exceed the base rate"
    # neutral defaults: no region + no timeline → global-average index (1.00), no escalation → base rates
    neutral, nmeta = cost_db.rates_for_project(db, proj)
    assert neutral["IfcWall"] == rates["IfcWall"] and nmeta["combined_factor"] == 1.0, nmeta

    # parse_cost_rows: flat map + rows, tolerant rate keys, drops junk (no ifc_class / non-positive rate)
    assert cost_db.parse_cost_rows({"IfcWall": 180}) == [{"ifc_class": "IfcWall", "total_cost": 180.0}]
    rows = cost_db.parse_cost_rows([
        {"ifc_class": "IfcSlab", "rate": 55, "uom": "m2"},        # alt rate key + uom kept
        {"ifc_class": "IfcColumn", "cost": 0},                    # non-positive → dropped
        {"total_cost": 99},                                       # no ifc_class → dropped
        {"ifc_class": "IfcBeam", "unit_cost": "42", "description": "W-shape"}])
    got = {r["ifc_class"]: r for r in rows}
    assert set(got) == {"IfcSlab", "IfcBeam"}, got
    assert got["IfcSlab"]["uom"] == "m2" and got["IfcBeam"]["total_cost"] == 42.0, got

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

    from aec_data import massing  # noqa: E402
    c.post(f"/projects/{pid}/cost-vintage", json={"dataset_id": ds24_id})
    metrics = massing.compute_massing({"lot_width": 20, "lot_depth": 14, "far": 1.5,
                                       "floor_to_floor": 3.5, "height_limit": 10})
    ifc = Path(tempfile.gettempdir()) / "costdb_model.ifc"
    massing.generate_ifc(metrics, str(ifc), name="CostDB")
    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("m.ifc", ifc.read_bytes(), "application/octet-stream")})
    assert up.status_code == 200, up.text[:160]
    # --- custom cost book import (a firm's own rates) --------------------------------------------
    def cost_db_rates(_c, dsid):                       # read a vintage's {class: rate} map via the engine
        with SessionLocal() as _db:
            return cost_db.rates_for(_db, dsid)
    # flat {ifc_class: rate} map form
    ci = c.post("/cost/datasets/import-custom",
                json={"vintage": 2026, "name": "Acme rates", "rates": {"IfcWall": 999.0, "IfcColumn": 1234.0}})
    assert ci.status_code == 200, ci.text[:200]
    cbody = ci.json()
    assert cbody["origin"] == "custom" and cbody["is_latest"] and cbody["imported"] == 2, cbody
    cust_id = cbody["id"]
    assert cost_db_rates(c, cust_id)["IfcWall"] == 999.0, "custom rate installed"
    # re-import same (year) REPLACES in place (no duplicate vintage), and updates the rate
    ci2 = c.post("/cost/datasets/import-custom",
                 json={"vintage": 2026, "rows": [{"ifc_class": "IfcWall", "total_cost": 888.0, "uom": "m2"}]})
    assert ci2.json()["id"] == cust_id, "re-import replaces the same custom vintage"
    assert cost_db_rates(c, cust_id)["IfcWall"] == 888.0 and "IfcColumn" not in cost_db_rates(c, cust_id)
    # empty/invalid book is a 400, not a crash
    assert c.post("/cost/datasets/import-custom", json={"vintage": 2026, "rates": {}}).status_code == 400

    # SEC: with RBAC ON, importing a vintage requires a PLATFORM ADMIN — is_latest is a global flag, so
    # a lone project member must not be able to silently reprice every unpinned project's estimate.
    from aec_api import rbac as _rbac
    _saved = _rbac.RBAC_ON
    _rbac.RBAC_ON = True
    try:
        assert c.post("/cost/datasets/import", json={"vintage": 2028}).status_code == 403
        assert c.post("/cost/datasets/import-custom",
                      json={"vintage": 2028, "rates": {"IfcWall": 1.0}}).status_code == 403
    finally:
        _rbac.RBAC_ON = _saved

    est = c.get(f"/projects/{pid}/qto/by-floor").json()
    assert est.get("cost_vintage", {}).get("vintage_year") == 2024, est.get("cost_vintage")
    # the takeoff also carries the localization/escalation adjustment (neutral here — no market assumption)
    assert est.get("cost_adjustment", {}).get("vintage_year") == 2024, est.get("cost_adjustment")
    # and the cost-vintage endpoint previews the same adjustment without running a takeoff
    va = c.get(f"/projects/{pid}/cost-vintage").json()
    assert va["adjustment"]["combined_factor"] == 1.0, va["adjustment"]

print("COST-DB OK - offline public importer builds vintage-versioned datasets (one priced item per shipped "
      "benchmark, MasterFormat-coded); importing a newer vintage flips is_latest; re-import is idempotent "
      "(no dup rows); resolve handles latest/exact/nearest-fallback/strict; a project pins a vintage for "
      "reproducibility and resolves to latest when unpinned; rates localize by the region cost index and "
      "escalate from the vintage year (neutral 1.0 with no assumption); the takeoff + cost-vintage endpoint "
      "both carry the adjustment; a firm imports its OWN cost book as a custom vintage (flat map or rows, "
      "re-import replaces in place, empty book 400s); cloud request without a subscription falls back to "
      "public with a warning.")
