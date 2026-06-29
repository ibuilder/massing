"""Disposition + marketing — listing auto-fill from the proforma, the project appraisal endpoint,
the marketing/valuation reports, the RESO export seam, and the signed public listing link.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_marketing.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_marketing.db"
os.environ["STORAGE_DIR"] = "./test_storage_marketing"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_marketing.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api.main import app                # noqa: E402

ASSUMPTIONS = {
    "timing": {"construction_months": 18, "leaseup_months": 6, "hold_years": 7, "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront"},
        {"category": "hard", "name": "Hard costs", "amount": 18_000_000, "curve": "scurve"},
        {"category": "soft", "name": "Soft costs", "amount": 4_000_000, "curve": "scurve"},
    ],
    "debt": {"ltc": 0.6, "rate": 0.075, "points": 0.01},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 3_600_000, "other_income_annual": 200_000,
                   "opex_annual": 1_300_000, "reserves_annual": 90_000,
                   "stabilized_occ": 0.94, "credit_loss_pct": 0.01},
    "exit": {"exit_cap": 0.055, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": 0.08, "lp": 0.9, "gp": 0.1}, {"hurdle": None, "lp": 0.8, "gp": 0.2}]},
    "discount_rate": 0.10,
    "tax": {"income_tax_rate": 0.25, "depreciation_years": 27.5,
            "capital_gains_rate": 0.20, "niit_rate": 0.038, "recapture_rate": 0.25},
}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Riverside Lofts"}).json()["id"]
    # give the project some property facts (sqft drives $/SF + sales-comparison)
    c.put(f"/projects/{pid}/property", json={"sqft": 60_000, "num_units": 80, "city": "Austin", "state": "TX"})
    c.post("/proforma/scenarios", json={"name": "Base", "project_id": pid, "assumptions": ASSUMPTIONS})

    # --- listing auto-fill from the proforma (the off-plan advantage) ----------
    af = c.get(f"/projects/{pid}/listings/autofill")
    assert af.status_code == 200, af.text[:200]
    data = af.json()["data"]
    assert data["_source"] == "proforma", data
    assert data.get("noi") and data.get("cap_rate") and data.get("list_price"), data
    # cap_rate is expressed in % (exit_cap 0.055 -> 5.5)
    assert abs(data["cap_rate"] - 5.5) < 0.01, data["cap_rate"]
    # list_price ~ NOI / cap (income-approach value)
    assert abs(data["list_price"] - data["noi"] / 0.055) < 2.0, data

    # --- create the listing record from the auto-filled data -------------------
    lid = c.post(f"/projects/{pid}/modules/listing",
                 json={"data": {**data, "address": "Riverside Lofts", "asset_type": "Multifamily",
                                "virtual_tour_url": "https://example.com/tour"}}).json()["id"]

    # --- comparables feed the sales-comparison approach -----------------------
    for psf, cap in ((310, 5.4), (295, 5.6)):
        c.post(f"/projects/{pid}/modules/comparable",
               json={"data": {"address": f"Comp {psf}", "asset_type": "Multifamily",
                              "price_psf": psf, "cap_rate": cap, "price": psf * 60_000}})

    # --- tri-approach appraisal ----------------------------------------------
    ap = c.get(f"/projects/{pid}/appraisal").json()
    assert ap["cost"]["value"] > 0 and ap["income"]["value"] > 0 and ap["sales_comparison"]["value"] > 0, ap
    # income value ties to NOI / cap
    assert abs(ap["income"]["value"] - ap["inputs"]["stabilized_noi"] / 0.055) < 2.0, ap["income"]
    # cost approach = (hard+soft) replacement + land
    assert abs(ap["cost"]["replacement_cost_new"] - 22_000_000) < 1.0, ap["cost"]
    assert abs(ap["cost"]["land_value"] - 4_000_000) < 1.0, ap["cost"]
    # sales comparison used 2 comps at ~$300/SF × 60k SF
    assert ap["sales_comparison"]["comp_count"] == 2, ap["sales_comparison"]
    assert ap["reconciliation"]["value"] > 0 and len(ap["reconciliation"]["contributions"]) == 3, ap["reconciliation"]

    # --- save overrides (heavier income weight) persists + changes the result --
    base_val = ap["reconciliation"]["value"]
    saved = c.post(f"/projects/{pid}/appraisal",
                   json={"weights": {"income": 1.0, "cost": 0.0, "sales_comparison": 0.0},
                         "depreciation_pct": 0.0}).json()
    assert abs(saved["reconciliation"]["value"] - saved["income"]["value"]) < 1.0, saved["reconciliation"]
    # the saved override is read back by a plain GET
    again = c.get(f"/projects/{pid}/appraisal").json()
    assert abs(again["reconciliation"]["value"] - saved["income"]["value"]) < 1.0, again["reconciliation"]

    # --- RESO export seam (bridge to WPRealWise / MLS) ------------------------
    reso = c.get(f"/projects/{pid}/listings/{lid}/reso").json()["reso"]
    assert reso["StandardStatus"] and reso.get("ListPrice") and reso.get("VirtualTourURLUnbranded"), reso

    # --- Phase 4: WPRealWise / MLS syndication bridge -------------------------
    # off by default -> status not enabled, syndicate returns an actionable 422
    st = c.get("/re-syndication/status").json()
    assert st["enabled"] is False and "not configured" in st["message"], st
    blocked = c.post(f"/projects/{pid}/listings/{lid}/syndicate")
    assert blocked.status_code == 422 and "REALWISE_URL" in blocked.text, blocked.text
    # configure the bridge + stub the HTTP transport, then syndicate for real
    from aec_api import re_bridge
    os.environ["REALWISE_URL"] = "https://realwise.example"
    os.environ["REALWISE_API_KEY"] = "k-123"
    captured = {}

    def _fake_post(url, headers, payload):
        captured["url"] = url; captured["headers"] = headers; captured["payload"] = payload
        return {"id": 4242, "permalink": "https://realwise.example/listing/4242"}
    _orig = re_bridge.post_json
    re_bridge.post_json = _fake_post
    try:
        assert c.get("/re-syndication/status").json()["enabled"] is True
        res = c.post(f"/projects/{pid}/listings/{lid}/syndicate").json()
        assert res["status"] == "syndicated" and res["remote_id"] == 4242, res
        assert res["url"] == "https://realwise.example/listing/4242", res
        assert res["fields_pushed"] == len(reso), (res, reso)
        # the push hit the WPRealWise REST route with a Bearer token + ListingKey + the RESO fields
        assert captured["url"].endswith("/wp-json/realwise/v1/listings"), captured["url"]
        assert captured["headers"]["Authorization"] == "Bearer k-123", captured["headers"]
        assert captured["payload"]["ListingKey"] and captured["payload"]["StandardStatus"], captured["payload"]
    finally:
        re_bridge.post_json = _orig
        os.environ.pop("REALWISE_URL", None); os.environ.pop("REALWISE_API_KEY", None)

    # --- Report Center: valuation + listing fact sheet + flyer render valid PDFs
    cat = {x["id"] for x in c.get("/reports").json()["reports"]}
    assert {"appraisal", "listing_factsheet", "marketing_flyer"} <= cat, cat
    for rid in ("appraisal", "listing_factsheet", "marketing_flyer"):
        pdf = c.get(f"/projects/{pid}/reports/{rid}.pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 1200, (rid, pdf.status_code)

    # --- signed public listing link: valid sig passes, missing/forged is 403 ---
    share = c.post(f"/projects/{pid}/listings/{lid}/share").json()
    assert share["url"].startswith(f"/projects/{pid}/listings/{lid}/public?sig="), share
    pub = c.get(share["url"])
    assert pub.status_code == 200 and pub.json()["listing"]["list_price"], pub.text[:200]
    assert "noi" not in pub.json()["listing"]                      # internal financials not published
    assert c.get(f"/projects/{pid}/listings/{lid}/public").status_code == 403           # no signature
    assert c.get(f"/projects/{pid}/listings/{lid}/public?sig=forged&exp=9999999999").status_code == 403

print("MARKETING OK - listing auto-fills from proforma (NOI/cap/price); tri-approach appraisal "
      "(cost+income+sales) reconciles + override persists; RESO export shaped; WPRealWise syndication "
      "bridge gates off -> 422, pushes RESO+ListingKey+Bearer when configured; valuation + fact-sheet + "
      "flyer PDFs render; signed public link passes, forged/absent -> 403")
