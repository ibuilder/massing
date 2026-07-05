"""Discipline Spine D1 — the shared vocabularies (NCS disciplines + MasterFormat divisions + Uniformat
crosswalk) that thread model → sheets → specs → bid packages → budget together.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_disciplines.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_disciplines.db"
os.environ["STORAGE_DIR"] = "./test_storage_disciplines"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_disciplines.db"):
    os.remove("./test_disciplines.db")

from fastapi.testclient import TestClient            # noqa: E402
from aec_api import classification as c              # noqa: E402
from aec_api.main import app                         # noqa: E402

# --- discipline derived from IFC class via its MasterFormat section ---
assert c.discipline_of_ifc_class("IfcColumn") == "S", c.discipline_of_ifc_class("IfcColumn")   # 03 → Structural
assert c.discipline_of_ifc_class("IfcDuctSegment") == "M", c.discipline_of_ifc_class("IfcDuctSegment")  # 23 → Mech
assert c.discipline_of_ifc_class("IfcPipeSegment") == "P", c.discipline_of_ifc_class("IfcPipeSegment")  # 22 → Plumb
assert c.discipline_of_ifc_class("IfcDoor") == "A", c.discipline_of_ifc_class("IfcDoor")        # 08 → Architectural

# --- division / discipline helpers ---
assert c.division_of("03 30 00") == "03", c.division_of("03 30 00")
assert c.division_of("26 05 19") == "26"
assert c.discipline_of_division("05") == "S" and c.discipline_of_division("26") == "E"

# --- legacy free-text enum normalization (rfi's "MEP" / "Geotechnical" / "Low Voltage") ---
assert c.discipline_code("MEP") == "M" and c.discipline_code("Geotechnical") == "C"
assert c.discipline_code("Low Voltage") == "T" and c.discipline_code("Structural") == "S"
assert c.discipline_code("S") == "S" and c.discipline_code("") is None

# --- catalogs ---
disc = c.disciplines()
assert len(disc) == 11 and disc[0]["code"] == "G", len(disc)
struct = next(d for d in disc if d["code"] == "S")
assert struct["divisions"] == ["03", "04", "05"] and "A" in struct["uniformat"], struct
assert len(c.masterformat_divisions()) == 25
# Uniformat → MasterFormat crosswalk (concept budget → procurement budget)
xw = {x["code"]: x["masterformat_divisions"] for x in c.uniformat_crosswalk()}
assert xw["D30"] == ["23"] and xw["A"] == ["03", "31"], xw

# --- the reference endpoint the UI selects + spine joins read ---
with TestClient(app) as cl:
    r = cl.get("/reference/disciplines").json()
    assert len(r["disciplines"]) == 11 and len(r["masterformat_divisions"]) == 25, r
    assert any(d["code"] == "S" and d["name"] == "Structural" for d in r["disciplines"])
    assert len(r["uniformat_crosswalk"]) == 13

    # --- D2: element → discipline derived from IFC class, over the property index ---
    import json as _json
    pid = cl.post("/projects", json={"name": "Discipline Model"}).json()["id"]
    elements = [
        {"guid": "c1", "ifc_class": "IfcColumn", "name": "Col 1", "storey": "L1"},   # → Structural
        {"guid": "s1", "ifc_class": "IfcSlab", "name": "Slab 1", "storey": "L1"},     # → Structural
        {"guid": "d1", "ifc_class": "IfcDoor", "name": "Door 1", "storey": "L1"},     # → Architectural
        {"guid": "m1", "ifc_class": "IfcDuctSegment", "name": "Duct 1", "storey": "L1"},   # → Mechanical
        {"guid": "p1", "ifc_class": "IfcPipeSegment", "name": "Pipe 1", "storey": "L1"},   # → Plumbing
    ]
    props = _json.dumps({"elements": elements}).encode()
    up = cl.post(f"/projects/{pid}/properties/index",
                 files={"file": ("props.json", props, "application/json")})
    assert up.status_code == 200 and up.json()["loaded"] == 5, up.text[:160]

    # filter by discipline (accepts a name or an NCS code); each element carries its derived discipline
    st = cl.get(f"/projects/{pid}/elements?discipline=Structural").json()
    assert len(st) == 2 and all(e["discipline"] == "Structural" for e in st), st
    assert len(cl.get(f"/projects/{pid}/elements?discipline=S").json()) == 2      # code works too
    assert len(cl.get(f"/projects/{pid}/elements?discipline=Mechanical").json()) == 1

    # model composition by discipline, in NCS sheet order (Structural before Architectural before MEP)
    comp = cl.get(f"/projects/{pid}/elements/by-discipline").json()
    assert comp["total"] == 5, comp
    names = [d["discipline"] for d in comp["disciplines"]]
    assert names.index("Structural") < names.index("Architectural") < names.index("Mechanical"), names
    struct = next(d for d in comp["disciplines"] if d["discipline"] == "Structural")
    assert struct["count"] == 2 and struct["code"] == "S", struct

    # discipline is a colour-by facet + bucketing
    facets = cl.get(f"/projects/{pid}/elements/facets-list").json()
    assert any(a["prop"] == "discipline" for a in facets["attributes"]), facets["attributes"]
    cb = cl.get(f"/projects/{pid}/elements/color-by?prop=discipline").json()
    assert cb["colored"] == 5 and {b["label"] for b in cb["buckets"]} >= {"Structural", "Mechanical"}, cb

    # --- D3: NCS sheet IDs + discipline-ordered drawing set ---
    for sheet, title in [("M-301", "HVAC Sections"), ("A-101", "Floor Plan"), ("S-201", "Framing")]:
        r = cl.post(f"/projects/{pid}/modules/drawing",
                    json={"data": {"number": sheet, "sheet_number": sheet, "title": title}})
        assert r.status_code == 201, r.text[:160]
    reg = cl.get(f"/projects/{pid}/drawing-set").json()
    # the bound set is ordered by NCS discipline (Structural → Architectural → Mechanical), even though
    # no discipline field was entered — it's parsed from the sheet number.
    order = [(s["sheet_number"], s["discipline"]) for s in reg["sheet_index"]]
    assert order == [("S-201", "Structural"), ("A-101", "Architectural"), ("M-301", "Mechanical")], order
    a101 = next(s for s in reg["sheet_index"] if s["sheet_number"] == "A-101")
    assert a101["sheet_id"]["discipline"] == "Architectural", a101["sheet_id"]
    assert a101["sheet_id"]["sheet_type_name"] == "Plans" and a101["sheet_id"]["sequence"] == "01", a101
    assert reg["by_discipline"].get("Structural") == 1, reg["by_discipline"]

    # --- D4: connect the procurement chain — spec → bid package → cost code → budget traceability ---
    cc = cl.post(f"/projects/{pid}/modules/cost_code",
                 json={"data": {"code": "03 30 00", "division": "03 — Concrete"}}).json()["id"]
    bp = cl.post(f"/projects/{pid}/modules/bid_package",
                 json={"data": {"name": "Concrete", "discipline": "Structural", "cost_code": cc,
                                "budget": 500000}}).json()["id"]
    cl.post(f"/projects/{pid}/modules/spec_section",
            json={"data": {"section_number": "03 30 00", "title": "CIP Concrete",
                           "division": "03 — Concrete", "bid_package": bp}})
    cl.post(f"/projects/{pid}/modules/spec_section",   # div 09 → Architectural, no package (a gap)
            json={"data": {"section_number": "09 20 00", "title": "Gypsum Board", "division": "09 — Finishes"}})
    tr = cl.get(f"/projects/{pid}/spine/traceability").json()
    cov = tr["coverage"]
    assert cov["specs"] == 2 and cov["specs_packaged_pct"] == 50.0, cov          # one spec unpackaged
    assert cov["packages_costed_pct"] == 100.0 and cov["spec_to_budget_pct"] == 50.0, cov
    assert len(tr["gaps"]["specs_without_bid_package"]) == 1, tr["gaps"]
    # the concrete spec traces all the way to the cost code
    concrete = next(c for c in tr["chain"] if c["section"] == "03 30 00")
    assert concrete["linked"] and concrete["bid_package_name"] == "Concrete" and concrete["cost_code_value"] == "03 30 00", concrete
    # discipline derived from division even when the field is blank (09 → Architectural)
    disc = {d["discipline"]: d for d in tr["disciplines"]}
    assert disc["Structural"]["packages"] == 1 and disc["Architectural"]["specs"] == 1, tr["disciplines"]

    # --- D5: generating a project seeds a fully-connected spine skeleton (model → budget traceable) ---
    from aec_api.db import SessionLocal                      # noqa: E402
    from aec_api.routers.generate import _seed_gc_portal     # noqa: E402
    gp = cl.post("/projects", json={"name": "Generated"}).json()["id"]
    with SessionLocal() as _db:
        seeded = _seed_gc_portal(_db, gp, type("B", (), {"hard_cost_psf": 300})(),
                                 {"buildable_gfa_sf": 100000, "floors": 10}, "sys")
        _db.commit()
    assert seeded["seeded"], seeded
    gtr = cl.get(f"/projects/{gp}/spine/traceability").json()
    gc = gtr["coverage"]
    # every seeded spec reaches a bid package, a cost code and the budget — 100% traceable out of the box
    assert gc["specs"] >= 4 and gc["specs_packaged_pct"] == 100.0, gc
    assert gc["packages_costed_pct"] == 100.0 and gc["spec_to_budget_pct"] == 100.0, gc
    assert all(c["linked"] for c in gtr["chain"]), [c for c in gtr["chain"] if not c["linked"]]
    gdisc = {d["discipline"]: d for d in gtr["disciplines"]}
    assert gdisc["Structural"]["budget"] > 0 and gdisc["Mechanical"]["packages"] == 1, gtr["disciplines"]

print("DISCIPLINES OK - NCS discipline vocabulary (11) + MasterFormat divisions (25) + Uniformat "
      "crosswalk (13); IFC-class->discipline (Column->S, Duct->M, Pipe->P, Door->A); legacy enum "
      "aliases (MEP->M, Geotechnical->C, Low Voltage->T) normalized; /reference/disciplines serves it")
