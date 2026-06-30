"""Specifications -> submittals: spec register, the spec-driven submittal log with missing-submittal
gaps, and AI/rules extraction of submittals from spec text.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_specs.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_specs.db"
os.environ["STORAGE_DIR"] = "./test_storage_specs"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)        # force the deterministic rules path
for _f in ("./test_specs.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import specs                  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app               # noqa: E402

# --- pure helpers ------------------------------------------------------------
assert specs.classify_type("Shop Drawings: reinforcement placing drawings") == "Shop Drawing"
assert specs.classify_type("Product Data for each mix design") == "Product Data"
assert specs.classify_type("Operation and Maintenance Data") == "O&M Manual"
assert specs.parse_section_number("SECTION 03 30 00 - CAST-IN-PLACE CONCRETE") == "03 30 00"

SPEC_TEXT = (
    "SECTION 03 30 00 - CAST-IN-PLACE CONCRETE\n"
    "1.3 SUBMITTALS\n"
    "  A. Product Data: For each type of manufactured material and product.\n"
    "  B. Shop Drawings: Placing drawings for steel reinforcement.\n"
    "  C. Samples: For each exposed architectural finish.\n"
    "  D. Mix Designs: Concrete mix design calculations.\n"
    "  E. Material Certificates: Mill certificates for reinforcement.\n")
items = specs.parse_required_submittals(SPEC_TEXT)
types = {i["type"] for i in items}
assert {"Product Data", "Shop Drawing", "Sample", "Calculations", "Certificate"} <= types, items

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Specs"}).json()["id"]
    assert "spec_section" in {m["key"] for m in c.get("/modules").json()}

    # --- AI extract (rules fallback, no key) ---------------------------------
    ex = c.post(f"/projects/{pid}/specs/extract-submittals", json={"text": SPEC_TEXT}).json()
    assert ex["source"] == "rules" and len(ex["items"]) == 5, ex
    assert all(i.get("section_number") == "03 30 00" for i in ex["items"]), ex
    assert any(i["type"] == "Shop Drawing" for i in ex["items"]), ex

    # --- extract + create: builds the submittal log + a spec section ----------
    ex2 = c.post(f"/projects/{pid}/specs/extract-submittals",
                 json={"text": SPEC_TEXT, "create": True}).json()
    assert ex2["created_submittals"] == 5, ex2
    subs = c.get(f"/projects/{pid}/modules/submittal").json()
    assert len(subs) == 5, len(subs)
    assert "spec_section" in {m["key"] for m in c.get("/modules").json()}
    assert len(c.get(f"/projects/{pid}/modules/spec_section").json()) == 1   # one section created

    # --- spec-driven submittal log: 5 required, 5 logged, 0 missing ----------
    log = c.get(f"/projects/{pid}/specs/submittal-log").json()
    assert log["spec_count"] == 1 and log["required_total"] == 5, log
    assert log["logged_total"] == 5 and log["missing_total"] == 0, log
    assert log["coverage_pct"] == 100.0, log
    row = log["rows"][0]
    assert row["section_number"] == "03 30 00" and row["missing_count"] == 0, row

    # --- add a spec section with NO logged submittals -> missing gap ----------
    c.post(f"/projects/{pid}/modules/spec_section", json={"data": {
        "section_number": "07 92 00", "title": "Joint Sealants", "division": "07 - Thermal & Moisture",
        "submittals_required": "Product Data: sealant; Samples: color; Warranty: 5-year."}})
    log2 = c.get(f"/projects/{pid}/specs/submittal-log").json()
    assert log2["spec_count"] == 2 and log2["missing_total"] == 3, log2     # 07 92 00 has 3 required, 0 logged
    js = next(r for r in log2["rows"] if r["section_number"] == "07 92 00")
    assert js["required_count"] == 3 and js["logged_count"] == 0 and js["missing_count"] == 3, js

    # --- report renders -------------------------------------------------------
    assert "spec_submittal_log" in {x["id"] for x in c.get("/reports").json()["reports"]}
    pdf = c.get(f"/projects/{pid}/reports/spec_submittal_log.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code

print("SPECS OK - submittal-type classifier + MasterFormat section parse; rules extractor pulls 5 typed "
      "submittals from a spec (section 03 30 00); extract+create builds the submittal log + spec section; "
      "spec-driven log reconciles required vs logged (100% then a 3-missing gap on 07 92 00); report renders")
