"""openBIM quality scoring — LOIN per element, IDS compliance %, export health, bSDD alignment.
Pure functions over a synthetic properties index (no live model needed).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_openbim_quality.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_openbim.db")
os.environ.pop("AEC_RBAC", None)

from aec_api import ids_authoring, openbim_quality      # noqa: E402

# synthetic index: 2 fully-specified walls, 1 bare wall, 1 proxy element
IDX = {
    "g1": {"ifc_class": "IfcWall", "type_name": "WT-1",
           "psets": {"Pset_WallCommon": {"FireRating": "2HR", "LoadBearing": True,
                                         "IsExternal": True, "ThermalTransmittance": 0.25}},
           "qtos": {"Qto_WallBaseQuantities": {"NetVolume": 3.2}}},
    "g2": {"ifc_class": "IfcWall", "type_name": "WT-1",
           "psets": {"Pset_WallCommon": {"FireRating": "2HR", "LoadBearing": True,
                                         "IsExternal": False, "ThermalTransmittance": 0.3}},
           "qtos": {"Qto_WallBaseQuantities": {"NetVolume": 2.1}}},
    "g3": {"ifc_class": "IfcWall", "type_name": "", "psets": {}, "qtos": {}},      # bare
    "g4": {"ifc_class": "IfcBuildingElementProxy", "type_name": "", "psets": {}, "qtos": {}},  # proxy
}

# --- LOIN --------------------------------------------------------------------------------------
lo = openbim_quality.loin(IDX)
assert lo["total"] == 4 and lo["max_score"] == 5, lo
# g1/g2 score 5 (geom+type+class+props+qtos); g3/g4 score 1 (geometry only)
assert lo["distribution"][5] == 2 and lo["distribution"][1] == 2, lo["distribution"]
assert lo["coordinated_pct"] == 50.0, lo["coordinated_pct"]      # 2 of 4 reach >=4 facets
assert lo["facet_coverage_pct"]["properties"] == 50.0, lo["facet_coverage_pct"]

# --- IDS compliance against the fire-life-safety use case --------------------------------------
specs = ids_authoring.specs_for_use_case("fire_life_safety")
assert specs, "expected specs for fire_life_safety"
comp = openbim_quality.ids_compliance(IDX, specs)
wall_spec = next(s for s in comp["specs"] if s["ifc_class"] == "IFCWALL")
assert wall_spec["applicable"] == 3, wall_spec        # 3 IfcWall elements (proxy excluded)
assert wall_spec["passing"] == 2, wall_spec           # only g1/g2 carry all required wall props
assert wall_spec["pct"] == 66.7, wall_spec

# --- export health: 1 of 4 is a proxy ----------------------------------------------------------
eh = openbim_quality.export_health(IDX)
assert eh["proxy_count"] == 1, eh
non_proxy = next(c for c in eh["checks"] if c["key"] == "non_proxy")
assert non_proxy["pct"] == 75.0, non_proxy            # 3 of 4 non-proxy
assert eh["overall"] in ("warn", "fail"), eh["overall"]   # thin coverage → not a clean pass

# --- bSDD alignment: 2 of 4 carry a type -------------------------------------------------------
bs = openbim_quality.bsdd_alignment(IDX)
assert bs["alignment_pct"] == 50.0, bs

# --- summary bundles everything ----------------------------------------------------------------
s = openbim_quality.summary(IDX, specs)
assert "loin" in s and "ids" in s and "export_health" in s and "bsdd" in s, list(s)

print("OPENBIM QUALITY OK - LOIN 2x5/2x1 (50% coordinated); IDS walls 2/3 pass (66.7%); "
      "export health flags 1 proxy (75% non-proxy); bSDD 50% classified")
