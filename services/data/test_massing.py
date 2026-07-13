"""Generative massing: pure zoning math + a from-scratch IFC round-trip.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_massing.py"""
import os
import tempfile
import warnings

warnings.filterwarnings("ignore")

from aec_data import massing  # noqa: E402

# --- pure zoning math --------------------------------------------------------
# 50 x 40 lot (2000 m2), FAR 3 -> 6000 m2 buildable. Setbacks 3 side / 6 front+rear.
# Plate = (50-6) x (40-12) = 44 x 28 = 1232 m2, but coverage 0.6 caps it at 1200 m2.
m = massing.compute_massing({
    "lot_width": 50, "lot_depth": 40, "far": 3.0, "coverage_max": 0.6,
    "front_setback": 6, "rear_setback": 6, "side_setback": 3,
    "floor_to_floor": 3.5, "efficiency": 0.8, "avg_unit_m2": 75,
})
assert m["lot_area_m2"] == 2000.0, m["lot_area_m2"]
assert abs(m["footprint_m2"] - 1200.0) < 1.0, m["footprint_m2"]      # coverage-capped
assert m["floors"] == 5, m["floors"]                                  # ceil(6000/1200) = 5
assert abs(m["buildable_gfa_m2"] - 6000.0) < 5.0, m["buildable_gfa_m2"]
assert m["binding_constraint"] in ("FAR", "coverage"), m["binding_constraint"]
assert m["units"] == int(6000 * 0.8 / 75), m["units"]                 # 64 units

# height limit binds before FAR: 14m / 3.5 = 4 floors (not 5)
mh = massing.compute_massing({"lot_area": 2000, "far": 3.0, "height_limit": 14, "floor_to_floor": 3.5})
assert mh["floors"] == 4 and mh["binding_constraint"] == "height", mh

# area-only input (no width/depth) still solves
ma = massing.compute_massing({"lot_area": 1000, "far": 2.0})
assert ma["floors"] >= 1 and ma["buildable_gfa_m2"] > 0, ma

# lot polygon (real parcel): shoelace area drives the program — a 50×40 rect polygon == lot_area 2000
mp = massing.compute_massing({"lot_polygon": [[0, 0], [50, 0], [50, 40], [0, 40]], "far": 3.0})
assert abs(mp["lot_area_m2"] - 2000.0) < 1.0, mp["lot_area_m2"]
# an L-shaped parcel has less area than its bounding box (1600 vs 2500)
lshape = massing.compute_massing({"lot_polygon": [[0, 0], [50, 0], [50, 20], [20, 20], [20, 50], [0, 50]], "far": 2.0})
assert abs(lshape["lot_area_m2"] - 1600.0) < 1.0, lshape["lot_area_m2"]

# true inward polygon offset (real setback footprint, not the bounding box):
sq = [[0, 0], [50, 0], [50, 40], [0, 40]]
assert abs(massing._polygon_area(massing.offset_polygon(sq, 5)) - 1200.0) < 1.0   # 40×30 inset
# compute_massing applies the offset to the parcel footprint (coverage relaxed so the offset binds)
mo = massing.compute_massing({"lot_polygon": sq, "far": 3.0, "side_setback": 5, "coverage_max": 0.99})
assert abs(mo["footprint_m2"] - 1200.0) < 5.0 and len(mo["buildable_polygon"]) == 4, mo["footprint_m2"]
# a setback deeper than the parcel collapses → zero buildable area (no crash, no inside-out polygon)
collapsed = massing.compute_massing({"lot_polygon": sq, "far": 3.0, "side_setback": 40})
assert collapsed["footprint_m2"] == 0.0 and collapsed["buildable_polygon"] == [], collapsed["footprint_m2"]

# bad input is rejected
try:
    massing.compute_massing({"far": 2.0})
    assert False, "expected ValueError for missing lot"
except ValueError:
    pass

# --- IFC round-trip (needs ifcopenshell; skip cleanly if absent) -------------
try:
    import ifcopenshell  # noqa: F401
    _have_ifc = True
except ImportError:
    _have_ifc = False

if _have_ifc:
    from aec_data.ifc_loader import open_model
    fd, path = tempfile.mkstemp(suffix=".ifc"); os.close(fd)
    try:
        massing.generate_ifc(m, path, name="Test Massing")
        model = open_model(path)
        storeys = model.by_type("IfcBuildingStorey")
        spaces = model.by_type("IfcSpace")
        slabs = model.by_type("IfcSlab")
        assert len(storeys) == m["floors"], (len(storeys), m["floors"])
        assert len(spaces) == m["floors"], (len(spaces), m["floors"])
        assert len(slabs) == m["floors"], (len(slabs), m["floors"])   # renderable floor plate per level
        assert model.by_type("IfcProject") and model.by_type("IfcSite") and model.by_type("IfcBuilding")
        # spaces carry area; slabs (physical) carry the visible geometry the viewer renders
        assert all(s.Representation is not None for s in spaces), "spaces missing geometry"
        assert all(s.Representation is not None for s in slabs), "slabs missing geometry"
        # geometry must be at metre scale (regression: default mm units shrank the model 1000x)
        import ifcopenshell.geom
        import ifcopenshell.util.unit as _uu
        assert abs(_uu.calculate_unit_scale(model) - 1.0) < 1e-9, "model must be in metres"
        sh = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), slabs[0])
        xs = sh.geometry.verts[0::3]
        span = max(xs) - min(xs)
        assert span > 5.0, f"slab too small ({span:.3f} m) — unit/scale regression"
        # M1: real IFC materials + surface-style colours applied
        assert len(model.by_type("IfcMaterial")) >= 1 and len(model.by_type("IfcSurfaceStyle")) >= 1, "materials/styles missing"
        assert len(model.by_type("IfcStyledItem")) > 0, "no styled representation items"
        print(f"IFC OK - {len(storeys)} storeys, {len(spaces)} floor-plate spaces + "
              f"{len(slabs)} renderable slabs, sited + represented + "
              f"{len(model.by_type('IfcMaterial'))} materials / {len(model.by_type('IfcSurfaceStyle'))} styles")

        # --- generative structural frame (frame=True) -----------------------
        fd2, fpath = tempfile.mkstemp(suffix=".ifc"); os.close(fd2)
        try:
            massing.generate_ifc(m, fpath, name="Framed", frame=True, bay=7.5)
            fm = open_model(fpath)
            gx = massing.gridlines(m["plate_w"], 7.5); gy = massing.gridlines(m["plate_d"], 7.5)
            exp_cols = len(gx) * len(gy) * m["floors"]
            exp_beams = (len(gy) * (len(gx) - 1) + len(gx) * (len(gy) - 1)) * m["floors"]
            cols, beams = fm.by_type("IfcColumn"), fm.by_type("IfcBeam")
            assert len(cols) == exp_cols, (len(cols), exp_cols)
            assert len(beams) == exp_beams, (len(beams), exp_beams)
            assert all(c.Representation is not None for c in cols), "columns missing geometry"
            ch = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), cols[0])
            zs = ch.geometry.verts[2::3]
            assert max(zs) - min(zs) > 2.0, "column height not metre-scale"
            print(f"FRAME OK - {len(cols)} columns + {len(beams)} beams on a {len(gx)}x{len(gy)} grid")
        finally:
            os.remove(fpath)

        # --- per-floor column taper + lateral core (R3 → geometry) ----------
        fd6, tpath = tempfile.mkstemp(suffix=".ifc"); os.close(fd6)
        try:
            # base floor 900 mm tapering to 500 mm at the top; thick 400 mm shear-core walls
            sched = [900, 800, 700, 600, 500]                   # one per floor, base first
            mem = {"column_schedule_mm": sched,
                   "lateral_core": {"plan_w_m": 6.0, "plan_d_m": 6.0, "wall_mm": 400}}
            massing.generate_ifc(m, tpath, name="Tapered", frame=True, core=True, bay=7.5, members=mem)
            tm = open_model(tpath)
            gset = ifcopenshell.geom.settings()

            def _xspan(el):                                     # world-space X extent of an element's mesh
                sh = ifcopenshell.geom.create_shape(gset, el)
                xs = sh.geometry.verts[0::3]
                return max(xs) - min(xs)

            tcols = tm.by_type("IfcColumn")
            # group columns by storey elevation → each floor's column width
            by_elev: dict[float, float] = {}
            for c in tcols:
                z = round(c.ObjectPlacement.RelativePlacement.Location.Coordinates[2], 1)
                by_elev.setdefault(z, _xspan(c))
            widths = [by_elev[z] for z in sorted(by_elev)]      # base → top
            assert len(widths) == m["floors"], (len(widths), m["floors"])
            # base column is widest, top is narrowest — the frame tapers as designed
            assert widths[0] > widths[-1] + 0.1, ("taper base>top", widths)
            assert all(widths[k] >= widths[k + 1] - 1e-6 for k in range(len(widths) - 1)), widths
            assert abs(widths[0] - 0.9) < 0.05 and abs(widths[-1] - 0.5) < 0.05, widths
            # lateral core: walls are the 400 mm shear-wall spec, not the 200 mm default.
            # thickness lives on the geometry (the thinner plan dimension of the wall box)
            def _wall_thk(w):
                sh = ifcopenshell.geom.create_shape(gset, w)
                xs = sh.geometry.verts[0::3]; ys = sh.geometry.verts[1::3]
                return min(max(xs) - min(xs), max(ys) - min(ys))
            core_walls = tm.by_type("IfcWall")
            thk = min(_wall_thk(w) for w in core_walls)
            assert abs(thk - 0.4) < 0.06, ("shear-wall thickness ~400mm", thk)
            print(f"TAPER OK - columns {widths[0]:.2f}->{widths[-1]:.2f} m base->top; "
                  f"lateral core walls {thk*1000:.0f} mm")
        finally:
            os.remove(tpath)

        # --- unit subdivision (units=True) ----------------------------------
        fd3, upath = tempfile.mkstemp(suffix=".ifc"); os.close(fd3)
        try:
            massing.generate_ifc(m, upath, name="Unitized", units=True)
            um = open_model(upath)
            upf = max(1, round(m["units"] / m["floors"]))
            uspaces = [s for s in um.by_type("IfcSpace")]
            assert len(uspaces) == upf * m["floors"], (len(uspaces), upf * m["floors"])
            # every unit space carries a real area
            import ifcopenshell.util.element as _ue
            areas = [(_ue.get_pset(s, "Qto_SpaceBaseQuantities") or {}).get("NetFloorArea") for s in uspaces]
            assert all(a and a > 0 for a in areas), "unit space missing area"
            print(f"UNITS OK - {len(uspaces)} unit spaces ({upf}/floor x {m['floors']} floors), each with area")
        finally:
            os.remove(upath)

        # --- envelope (facade walls + windows feed the energy model) --------
        fd4, epath = tempfile.mkstemp(suffix=".ifc"); os.close(fd4)
        try:
            massing.generate_ifc(m, epath, name="Enclosed", envelope=True, wwr=0.4)
            em = open_model(epath)
            assert len(em.by_type("IfcWall")) == 4 * m["floors"], len(em.by_type("IfcWall"))
            assert len(em.by_type("IfcWindow")) == 4 * m["floors"], len(em.by_type("IfcWindow"))
            from aec_data import energy
            e = energy.analyze_file(epath)
            assert e["areas_m2"]["window"] > 0 and e["areas_m2"]["exterior_wall_net"] > 0, e["areas_m2"]
            assert e["ua_w_per_k"]["total"] > 0, e["ua_w_per_k"]
            # M3: Revit-style layered assemblies on walls + slabs (IfcMaterialLayerSet + usage)
            lsets = em.by_type("IfcMaterialLayerSet")
            usages = em.by_type("IfcMaterialLayerSetUsage")
            assert len(lsets) >= 2 and len(em.by_type("IfcMaterialLayer")) >= 6, (len(lsets),)
            # every wall + slab carries a layer-set usage (4 walls/floor + 1 slab/floor)
            assert len(usages) == (4 + 1) * m["floors"], (len(usages), m["floors"])
            # C2: model-derived COBie field depth — areas on Space, asset fields on Type/Component,
            # and the Attribute sheet flattening remaining psets (Pset_WallCommon here).
            from aec_data import cobie
            sh = cobie.cobie_sheets(em)
            assert set(sh) >= {"Facility", "Floor", "Space", "Type", "Component", "Attribute"}, set(sh)
            assert any(s.get("GrossArea") for s in sh["Space"]), "COBie Space missing areas"
            assert all("Manufacturer" in t and "ExpectedLife" in t for t in sh["Type"]), "COBie Type fields"
            assert all("SerialNumber" in c and "AssetIdentifier" in c for c in sh["Component"]), "COBie Component fields"
            wall_attr = [a for a in sh["Attribute"] if a["Category"] == "Pset_WallCommon"]
            assert wall_attr and {"Name", "Value", "SheetName", "RowName"} <= set(wall_attr[0]), "Attribute sheet"
            print(f"ENVELOPE OK - {len(em.by_type('IfcWall'))} walls + {len(em.by_type('IfcWindow'))} windows; "
                  f"energy WWR {e['areas_m2']['window_wall_ratio']}, UA {e['ua_w_per_k']['total']} W/K; "
                  f"M3: {len(lsets)} layer sets, {len(usages)} usages; "
                  f"COBie: {len(sh['Attribute'])} attribute rows")
        finally:
            os.remove(epath)

        # --- corridor (double-loaded test-fit) unit layout ------------------
        fd6, lpath = tempfile.mkstemp(suffix=".ifc"); os.close(fd6)
        try:
            massing.generate_ifc(m, lpath, name="Corridor", units=True, unit_layout="corridor")
            lm = open_model(lpath)
            spaces = [s for s in lm.by_type("IfcSpace")]
            corridors = [s for s in spaces if (s.LongName or "") == "Corridor"]
            assert len(corridors) == m["floors"], "one corridor per floor"
            assert len(spaces) > len(corridors), "units placed alongside corridors"
            print(f"CORRIDOR OK - double-loaded layout: {len(corridors)} corridors + "
                  f"{len(spaces) - len(corridors)} unit spaces across {m['floors']} floors")
        finally:
            os.remove(lpath)

        # --- surface parking lot as real IfcSpace stalls (A2) ----------------
        pfd, ppath = tempfile.mkstemp(suffix=".ifc"); os.close(pfd)
        try:
            massing.generate_ifc(m, ppath, name="Parked", parking=40)
            pm = open_model(ppath)
            import ifcopenshell.util.element as _ue2
            stalls = [s for s in pm.by_type("IfcSpace")
                      if (_ue2.get_pset(s, "Pset_SpaceCommon") or {}).get("Reference") == "PARKING"]
            assert len(stalls) == 40, len(stalls)
            assert any(st.Name == "Site Parking" for st in pm.by_type("IfcBuildingStorey")), "parking storey"
            # each stall carries a real area (~2.5×5 m × 0.94²)
            areas = [(_ue2.get_pset(s, "Qto_SpaceBaseQuantities") or {}).get("NetFloorArea") for s in stalls]
            assert all(a and 9 < a < 13 for a in areas), areas[:3]
            print(f"PARKING OK - {len(stalls)} stalls as IfcSpace(PARKING) on a Site Parking storey, each with area")
        finally:
            os.remove(ppath)

        # --- service core + MEP risers (core=True) --------------------------
        fd5, cpath = tempfile.mkstemp(suffix=".ifc"); os.close(fd5)
        try:
            massing.generate_ifc(m, cpath, name="Cored", core=True)
            cm = open_model(cpath)
            assert len(cm.by_type("IfcTransportElement")) == m["floors"], "elevator per floor"
            # A2: two means of egress positioned for code — core stair + a remote egress stair / floor
            assert len(cm.by_type("IfcStair")) == 2 * m["floors"], "two egress stairs per floor"
            _snames = {s.Name for s in cm.by_type("IfcStair")}
            assert "Egress stair 1" in _snames and "Egress stair 2" in _snames, _snames
            # per floor: a vertical supply-air riser + a horizontal supply-air distribution main
            assert len(cm.by_type("IfcDuctSegment")) == 2 * m["floors"], "supply riser + air main per floor"
            # per floor: a plumbing riser + a domestic-water distribution main
            assert len(cm.by_type("IfcPipeSegment")) == 2 * m["floors"], "plumbing riser + water main per floor"
            assert len(cm.by_type("IfcWall")) == 4 * m["floors"], "core walls"
            print(f"CORE OK - elevator + 2 egress stairs (code-separated) + duct/pipe risers+mains + core walls across {m['floors']} floors")
        finally:
            os.remove(cpath)

        # --- takeoff cache (content-keyed by path+mtime) --------------------
        from aec_data import qto
        qto._TAKEOFF_CACHE.clear()
        r1 = qto.takeoff_file(path)
        r2 = qto.takeoff_file(path)
        assert r1 is r2, "second takeoff should be a cache hit (same object)"
        assert len(qto._TAKEOFF_CACHE) == 1, "one cache entry expected"
        import time as _t
        _t.sleep(0.01); os.utime(path, None)          # bump mtime → content-key changes → miss
        r3 = qto.takeoff_file(path)
        assert r3 is not r2, "mtime change should invalidate the cache"
        print("TAKEOFF CACHE OK - cache hit on repeat, invalidated on mtime change")
    finally:
        os.remove(path)

    # --- earth dome: hemispherical shell renders + carries floor area ----
    dfd, dpath = tempfile.mkstemp(suffix=".ifc"); os.close(dfd)
    try:
        massing.generate_dome_ifc(dpath, name="Earth Dome", radius=8.0)
        dm = open_model(dpath)
        assert len(dm.by_type("IfcRoof")) == 1 and len(dm.by_type("IfcTriangulatedFaceSet")) == 1, "dome shell"
        assert len(dm.by_type("IfcSlab")) == 1 and len(dm.by_type("IfcSpace")) == 1, "floor + interior"
        sh = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), dm.by_type("IfcRoof")[0])
        xs = sh.geometry.verts[0::3]
        assert abs((max(xs) - min(xs)) - 16.0) < 0.5, f"dome span ~2r ({max(xs)-min(xs):.1f})"
        met = massing.dome_metrics(8.0)
        assert met["floors"] == 1 and abs(met["footprint_m2"] - 201.06) < 1, met   # π·8²
        print(f"DOME OK - hemispherical shell ({len(sh.geometry.verts)//3} verts) + floor + interior; {met['buildable_gfa_sf']} sf")
    finally:
        os.remove(dpath)
else:
    print("IFC round-trip SKIPPED (ifcopenshell not importable in this interpreter)")

print("MASSING OK - zoning math (FAR/coverage/height binding, units, area-only, validation)")
