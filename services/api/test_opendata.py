"""Multi-city permit open data: city registry, normalization across differing schemas, the GIS
GeoJSON overlay, and the GC permit-module import (mapping + dedup). The Socrata HTTP layer is mocked
so the suite is offline/deterministic.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_opendata.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_opendata.db"
os.environ["STORAGE_DIR"] = "./test_storage_opendata"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_opendata.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient                      # noqa: E402
from aec_api.main import app                                   # noqa: E402
from aec_api import opendata                                   # noqa: E402

# canned upstream rows per dataset — real column names from each city's SODA endpoint
_FAKE = {
    "w9ak-ipjd": [{                       # NYC
        "job_filing_number": "B00123456", "job_type": "New Building", "filing_status": "Permit Issued",
        "proposed_dwelling_units": "12", "total_construction_floor_area": "21500", "initial_cost": "4,250,000",
        "filing_date": "2026-02-01T00:00:00", "approved_date": "2026-03-15T00:00:00",
        "job_description": "New 6-story residential building", "house_no": "120", "street_name": "MAIN ST",
        "borough": "BROOKLYN", "owner_s_business_name": "ACME Holdings LLC",
        "applicant_first_name": "Jane", "applicant_last_name": "Doe", "latitude": "40.6782", "longitude": "-73.9442"}],
    "ydr8-5enu": [{                       # Chicago (fee data + typed contacts + location point)
        "permit_": "100987654", "permit_type": "PERMIT - NEW CONSTRUCTION", "reported_cost": "1500000",
        "application_start_date": "2026-01-10", "issue_date": "2026-02-20", "total_fee": "12500.50",
        "work_description": "3-story masonry", "street_number": "401", "street_direction": "N",
        "street_name": "STATE ST", "contact_1_name": "BuildRight GC", "contact_2_name": "North LLC",
        "latitude": "41.8881", "longitude": "-87.6278",
        "location": {"type": "Point", "coordinates": [-87.6278, 41.8881]}}],
}


def fake_fetch(domain, dataset, where, q, order, limit):
    return list(_FAKE.get(dataset, []))


opendata._fetch = fake_fetch          # mock the only network call


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Permit Intel"}).json()["id"]

    # --- city registry -------------------------------------------------------
    cities = c.get("/opendata/permit-cities").json()["cities"]
    ids = {x["id"] for x in cities}
    assert {"nyc", "sf", "chicago", "la", "austin"} <= ids, ids
    austin = next(x for x in cities if x["id"] == "austin")
    nyc_city = next(x for x in cities if x["id"] == "nyc")
    assert austin["geo"] is False and nyc_city["geo"] is True, cities   # austin has no coords

    # --- normalization across schemas ---------------------------------------
    nyc = c.get(f"/projects/{pid}/opendata/permits", params={"city": "nyc"}).json()
    assert nyc["count"] == 1, nyc
    p = nyc["permits"][0]
    assert p["permit_number"] == "B00123456" and p["permit_type"] == "New Building", p
    assert p["est_cost"] == 4250000.0 and p["units"] == 12, p          # "$4,250,000" parsed; units int
    assert p["floor_area"] == 21500.0, p
    assert p["owner"] == "ACME Holdings LLC" and p["applicant"] == "Jane Doe", p
    assert p["address"] == "120 MAIN ST BROOKLYN", p
    assert abs(p["lat"] - 40.6782) < 1e-6 and p["issued_date"] == "2026-03-15", p

    chi = c.get(f"/projects/{pid}/opendata/permits", params={"city": "chicago"}).json()["permits"][0]
    assert chi["contractor"] == "BuildRight GC" and chi["owner"] == "North LLC", chi
    assert chi["fee"] == 12500.50 and chi["est_cost"] == 1500000.0, chi

    # --- GeoJSON overlay -----------------------------------------------------
    gj = c.get(f"/projects/{pid}/opendata/permits.geojson", params={"city": "chicago"}).json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == 1, gj
    assert gj["features"][0]["geometry"]["coordinates"] == [-87.6278, 41.8881], gj

    # --- GC permit-module import + dedup ------------------------------------
    imp = c.post(f"/projects/{pid}/opendata/permits/import", json={"city": "nyc"}).json()
    assert imp["imported"] == 1 and imp["skipped"] == 0, imp
    permits = c.get(f"/projects/{pid}/modules/permit").json()
    assert len(permits) == 1, permits
    d = permits[0]["data"]
    assert d["number"] == "B00123456" and d["source"] == "opendata" and d["source_city"] == "nyc", d
    assert d["permit_type"] == "Building" and d["status"] == "Issued", d   # mapped to module vocab
    assert d["expires"] and d["authority"].startswith("NYC"), d            # required field defaulted
    assert d["owner"] == "ACME Holdings LLC" and d["est_cost"] == 4250000.0, d  # rich fields preserved

    # re-import is idempotent (same number+city is skipped, not duplicated)
    again = c.post(f"/projects/{pid}/opendata/permits/import", json={"city": "nyc"}).json()
    assert again["imported"] == 0 and again["skipped"] == 1, again
    assert len(c.get(f"/projects/{pid}/modules/permit").json()) == 1

    # --- failure path: upstream error -> clean 502 ---------------------------
    def boom(*a, **k):
        raise opendata.OpendataError("feed down")
    opendata._fetch = boom
    assert c.get(f"/projects/{pid}/opendata/permits", params={"city": "sf"}).status_code == 502
    opendata._fetch = fake_fetch

print("OPENDATA OK - 5-city registry (austin no-geo); NYC+Chicago schemas normalize (cost/units/owner/"
      "contractor/fee/coords); GeoJSON overlay; GC permit import maps to module vocab + defaults expires + "
      "preserves rich fields + dedups on re-import; upstream failure -> 502")
