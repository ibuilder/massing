"""Generate a detailed ~30-story luxury residential tower (Quay-Tower-style) IFC:
cast-in-place concrete structure (columns/slabs/core walls/beams/footings + sample rebar), a punched
glazed facade, full MEP (risers for water/sanitary/storm/gas/electric + fire standpipe, sprinkler mains +
heads, base MEP plant rooms with switchgear/pumps/transformer, and utility POEs), residential apartments +
corridor/core, ground retail + lobby, top amenities, and a roof. Then generate plan SVGs.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe <this> (from services/api)
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = r"C:\Server\modelmaker"
for p in (os.path.join(_ROOT, "services", "data", "src"), os.path.join(_ROOT, "services", "api", "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

import ifcopenshell  # noqa: E402
import ifcopenshell.api  # noqa: E402
import ifcopenshell.util.unit as uu  # noqa: E402
import numpy as np  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

OUT = os.path.join(_HERE, "quay_tower.ifc")

# ---- parameters (Quay-Tower-style: ODA waterfront luxury condo) -----------------------------------
FP_W, FP_D = 34.0, 22.0            # floorplate: 34 m (E-W) x 22 m (N-S)
FLOOR_H = 3.2                      # floor-to-floor (m)
N_ABOVE = 30                       # above-grade levels (Level 1 ground ... Level 30 amenity)
CELLAR_Z = -4.5                    # below-grade plant/POE level
GX = [0.0, 8.5, 17.0, 25.5, 34.0]  # column grid X
GY = [0.0, 7.33, 14.67, 22.0]      # column grid Y
CORE = (13.0, 8.0, 21.0, 14.0)     # central elevator/stair core (x0,y0,x1,y1)
COL = 0.55                         # column size (m) — big concrete columns low, keep uniform for demo
WALL_T = 0.30                      # core shear-wall thickness
SLAB_T = 0.25                      # flat-slab thickness
t0 = time.time()
count = {"struct": 0, "facade": 0, "mep": 0, "space": 0, "misc": 0}


def lvl(model, i):
    """Storey name for above-grade level i (1-based)."""
    return model.by_type("IfcBuildingStorey")


def add_space(model, x0, y0, w, d, name, storey_name, height=3.0, occ="Residential"):
    scale = uu.calculate_unit_scale(model)
    st = next((s for s in model.by_type("IfcBuildingStorey") if s.Name == storey_name), None)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0)
    body = next((c for c in model.by_type("IfcGeometricRepresentationSubContext")
                 if c.ContextIdentifier == "Body"), None) or model.by_type("IfcGeometricRepresentationContext")[0]
    sp = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace", name=name)
    sp.LongName = name
    if hasattr(sp, "PredefinedType"):
        try:
            sp.PredefinedType = "INTERNAL"
        except Exception:
            pass
    m = np.eye(4); m[0, 3] = x0 + w / 2.0; m[1, 3] = y0 + d / 2.0; m[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=sp, matrix=m)
    prof = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=w / scale, YDim=d / scale)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body, profile=prof, depth=height)
    ifcopenshell.api.run("geometry.assign_representation", model, product=sp, representation=rep)
    if st:
        ifcopenshell.api.run("aggregate.assign_object", model, products=[sp], relating_object=st)
    qto = ifcopenshell.api.run("pset.add_qto", model, product=sp, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", model, qto=qto, properties={"NetFloorArea": round(w * d, 2),
                                                                       "GrossFloorArea": round(w * d, 2)})
    ps = ifcopenshell.api.run("pset.add_pset", model, product=sp, name="Pset_SpaceCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"OccupancyType": occ, "IsExternal": False})
    count["space"] += 1
    return sp.GlobalId


def main():
    print("== generating blank 30-storey shell ==")
    massing.generate_blank_ifc(OUT, name="Quay-style Residential Tower", storeys=N_ABOVE,
                               storey_height=FLOOR_H, ground_size=max(FP_W, FP_D) + 8)
    m = open_model(OUT)
    # a below-grade plant/POE level
    edit.add_storey(m, "Cellar", CELLAR_Z)
    storeys = {s.Name: s for s in m.by_type("IfcBuildingStorey")}
    L = [f"Level {i}" for i in range(1, N_ABOVE + 1)]
    print(f"   storeys: Cellar + {len(L)} above-grade")

    incore = lambda x, y: (CORE[0] - 0.1 <= x <= CORE[2] + 0.1 and CORE[1] - 0.1 <= y <= CORE[3] + 0.1)

    # ---- FOUNDATION (cellar) ----
    print("== foundation ==")
    for gx in GX:
        for gy in GY:
            if incore(gx, gy):
                continue
            edit.add_footing(m, [gx, gy], 2.2, 2.2, 0.7, "Cellar"); count["struct"] += 1
    # mat slab at cellar
    edit.add_slab(m, [[-2, -2], [FP_W + 2, -2], [FP_W + 2, FP_D + 2], [-2, FP_D + 2]], 0.6, "Cellar"); count["struct"] += 1

    # ---- STRUCTURE (every level) ----
    print("== structure: columns / slabs / core / beams (all floors) ==")
    levels_all = ["Cellar"] + L
    for name in levels_all:
        # columns
        for gx in GX:
            for gy in GY:
                if incore(gx, gy):
                    continue
                edit.add_column(m, [gx, gy], FLOOR_H, COL, COL, name); count["struct"] += 1
        # floor slab (flat plate)
        edit.add_slab(m, [[0, 0], [FP_W, 0], [FP_W, FP_D], [0, FP_D]], SLAB_T, name); count["struct"] += 1
        # core shear walls (4 sides of the core box)
        cx0, cy0, cx1, cy1 = CORE
        for a, b in (((cx0, cy0), (cx1, cy0)), ((cx1, cy0), (cx1, cy1)),
                     ((cx1, cy1), (cx0, cy1)), ((cx0, cy1), (cx0, cy0))):
            wg = edit.add_wall(m, list(a), list(b), FLOOR_H, WALL_T, name); count["struct"] += 1
            # the core is the exit-stair / elevator-shaft enclosure — a 2-hr fire barrier (IBC 713/1023)
            edit.set_element_pset(m, wg, "Pset_WallCommon", "FireRating", "2 HR", "string")
            edit.set_element_pset(m, wg, "Pset_WallCommon", "Compartmentation", True, "bool")
        # perimeter beams (edge grid spans)
        for i in range(len(GX) - 1):
            edit.add_beam(m, [GX[i], 0], [GX[i + 1], 0], 0.35, 0.6, name); count["struct"] += 1
            edit.add_beam(m, [GX[i], FP_D], [GX[i + 1], FP_D], 0.35, 0.6, name); count["struct"] += 1
        for j in range(len(GY) - 1):
            edit.add_beam(m, [0, GY[j]], [0, GY[j + 1]], 0.35, 0.6, name); count["struct"] += 1
            edit.add_beam(m, [FP_W, GY[j]], [FP_W, GY[j + 1]], 0.35, 0.6, name); count["struct"] += 1

    # sample rebar cage detail — a few Level 1 columns (LOD 400 demonstration)
    print("== sample rebar (LOD 400) ==")
    l1cols = [c for c in m.by_type("IfcColumn")][:6]
    for c in l1cols:
        try:
            edit.RECIPES["add_rebar_cage"](m, {"column_guid": c.GlobalId}); count["struct"] += 1
        except Exception as e:  # noqa: BLE001
            print("   rebar skip:", e); break

    # ---- FACADE: unitized CURTAIN WALL (IfcCurtainWall) — one full-height assembly per elevation.
    # A glazed facade is a curtain-wall system (mullions/transoms/panels as IfcMember/IfcPlate), not a
    # thin IfcWall with punched windows — so it reads as Architectural envelope + estimates as 08 44 00.
    print("== facade: unitized curtain wall ==")
    facade_top = N_ABOVE * FLOOR_H
    edges = [([0, 0], [FP_W, 0]), ([FP_W, 0], [FP_W, FP_D]),
             ([FP_W, FP_D], [0, FP_D]), ([0, FP_D], [0, 0])]
    for a, b in edges:
        try:
            edit.RECIPES["add_curtain_wall"](m, {"start": a, "end": b, "height": facade_top,
                                                 "cols": 6, "rows": N_ABOVE, "storey": "Level 1"})
            count["facade"] += 1
        except Exception as e:  # noqa: BLE001
            print("   curtain-wall skip -> glazed-wall fallback:", e)
            for name in L:
                w = edit.add_wall(m, a, b, FLOOR_H, 0.15, name); count["facade"] += 1
                edit.set_element_pset(m, w, "Pset_WallCommon", "IsExternal", True, "bool")

    m.write(OUT)
    print(f"   [{time.time()-t0:.0f}s] struct+facade done — {sum(count.values())} elements so far")

    # ---- MEP: risers (cellar->roof), sprinkler mains+heads, base plant + POEs ----
    print("== MEP risers + systems ==")
    top_z = N_ABOVE * FLOOR_H
    risers = [((22.0, 9.0), "Domestic Cold Water", "plumbing", 0.1),
              ((22.5, 9.0), "Domestic Hot Water", "plumbing", 0.08),
              ((22.0, 13.0), "Sanitary Waste", "plumbing", 0.15),
              ((22.5, 13.0), "Storm Leader", "stormwater", 0.15),
              ((14.0, 9.0), "Gas", "plumbing", 0.05),
              ((14.0, 13.0), "Fire Standpipe", "fire", 0.15),
              ((14.5, 9.0), "Electrical Bus Riser", "electrical", 0.2),
              ((14.5, 13.0), "Comms Riser", "communication", 0.1)]
    for (x, y), sysname, disc, size in risers:
        edit.add_riser(m, [x, y], CELLAR_Z, top_z, size, "IfcPipeSegment" if disc != "electrical" else "IfcCableCarrierSegment",
                       "Level 1", sysname, disc); count["mep"] += 1

    print("== sprinkler mains + heads (residential floors) ==")
    for name in L:
        li = int(name.split()[1])
        if li < 2:
            continue
        # a sprinkler branch main across the floor + heads on a grid
        edit.add_mep_run(m, "IfcPipeSegment", [14.5, 13.0], [30, 13.0], "round", 0.05, name, "Fire Protection", "fire"); count["mep"] += 1
        for hx in (6, 12, 24, 30):
            for hy in (5, 17):
                edit.add_fire_equipment(m, "sprinkler", [hx, hy], name); count["mep"] += 1

    # ---- FIRE ALARM (life-safety, distinct FA discipline) + TELECOM (T) ----
    print("== fire alarm (FA) + telecom (T) devices ==")
    # head-end equipment in the cellar: Fire Alarm Control Panel + telecom Main Distribution Frame
    edit.add_fa_device(m, "facp", [7.5, 3], "Cellar"); count["mep"] += 1
    edit.add_comms_device(m, "mdf", [7.5, 11], "Cellar"); count["mep"] += 1
    for name in L:
        li = int(name.split()[1])
        # smoke detectors (corridor + two units) + a manual pull station at the core exit + a horn/strobe
        for pt in ([12, 7], [6, 10], [28, 10]):
            edit.add_fa_device(m, "smoke_detector", pt, name); count["mep"] += 1
        edit.add_fa_device(m, "pull_station", [13.5, 7], name); count["mep"] += 1
        edit.add_fa_device(m, "horn_strobe", [17.5, 7], name); count["mep"] += 1
        # telecom: an IDF (floor comms closet) every ~5 floors + a wireless access point on each floor
        if li % 5 == 1:
            edit.add_comms_device(m, "idf", [13, 12], name); count["mep"] += 1
        edit.add_comms_device(m, "wap", [17, 10.5], name); count["mep"] += 1

    # ---- base MEP plant rooms + equipment + POEs (cellar) ----
    print("== base plant rooms + POE ==")
    add_space(m, 1, 1, 8, 6, "Main Electrical / Switchgear Room", "Cellar", 4.0, "Electrical")
    add_space(m, 1, 8, 7, 6, "Domestic Water / Booster Pump Room", "Cellar", 4.0, "Mechanical")
    add_space(m, 25, 1, 8, 6, "Fire Pump Room", "Cellar", 4.0, "Mechanical")
    add_space(m, 25, 8, 8, 7, "Boiler / Mechanical Room", "Cellar", 4.0, "Mechanical")
    add_space(m, 10, 16, 6, 5, "Storm / Sanitary Sump Room", "Cellar", 4.0, "Mechanical")
    # major plant equipment
    plant = [("IfcElectricDistributionBoard", [3, 3], "SWITCHGEAR", "Main Switchgear", "Electrical Service"),
             ("IfcTransformer", [6, 3], None, "Utility Transformer", "Electrical Service"),
             ("IfcPump", [3, 10], "SUBMERSIBLEPUMP", "Domestic Booster Pump", "Domestic Water"),
             ("IfcTank", [6, 10], "STORAGE", "Domestic Water Tank", "Domestic Water"),
             ("IfcPump", [28, 3], "ENDSUCTION", "Fire Pump", "Fire Protection"),
             ("IfcBoiler", [28, 10], "WATER", "Heating Boiler", "Heating"),
             ("IfcPump", [12, 18], "SUMPPUMP", "Storm Sump Pump", "Stormwater")]
    for cls, pt, pd, nm, sysn in plant:
        try:
            edit.add_mep_terminal(m, cls, pt, 1.2, 1.0, 1.8, pd, "Cellar", sysn,
                                  {"Electrical Service": "electrical", "Domestic Water": "plumbing",
                                   "Fire Protection": "fire", "Heating": "heating", "Stormwater": "stormwater"}.get(sysn))
            count["mep"] += 1
        except Exception as e:  # noqa: BLE001
            print("   plant skip", cls, e)
    # utility POEs — annotate the incoming service entries at the cellar wall
    for label, pt in [("POE: Water Service Entry", [0.5, 9]), ("POE: Electrical Service Entry", [0.5, 3]),
                      ("POE: Gas Service Entry", [0.5, 15]), ("POE: Storm Connection", [17, 21.5]),
                      ("POE: Sanitary/Sewer Connection", [20, 21.5])]:
        try:
            edit.add_annotation(m, pt, label, "callout", "Cellar", CELLAR_Z + 1.0); count["misc"] += 1
        except Exception as e:  # noqa: BLE001
            print("   POE skip", e)

    m.write(OUT)
    print(f"   [{time.time()-t0:.0f}s] MEP done — {sum(count.values())} elements")

    # ---- SPACES: apartments, corridor, retail/lobby, amenities ----
    print("== spaces: apartments / retail / amenities ==")
    for name in L:
        li = int(name.split()[1])
        h = 3.0
        if li == 1:
            add_space(m, 0.5, 0.5, 16, 21, "Retail — Commercial", name, 4.0, "Retail")
            add_space(m, 22, 0.5, 11.5, 21, "Residential Lobby", name, 4.0, "Lobby")
        elif li >= N_ABOVE - 1:      # top two floors: amenities
            add_space(m, 0.5, 0.5, 16, 21, "Amenity Lounge / Sky Club", name, h, "Amenity")
            add_space(m, 22, 0.5, 11.5, 10, "Fitness Center", name, h, "Amenity")
            add_space(m, 22, 11, 11.5, 10, "Roof Terrace / Landscaped Amenity", name, h, "Amenity")
        else:                        # residential: 4 apartments + corridor around the core
            add_space(m, 0.5, 0.5, 12, 7, f"Apt {li}A (2BR)", name, h)
            add_space(m, 0.5, 14.5, 12, 7, f"Apt {li}B (2BR)", name, h)
            add_space(m, 22, 0.5, 11.5, 7, f"Apt {li}C (3BR)", name, h)
            add_space(m, 22, 14.5, 11.5, 7, f"Apt {li}D (4BR penthouse-style)", name, h)
            add_space(m, 8.5, 6.5, 17, 1.2, f"Corridor L{li}", name, h, "Circulation")

    # ---- ARCHITECTURAL FINISHES: partitions, unit doors, ceilings, floor finishes, railings ----
    print("== finishes: partitions / doors / ceilings / floors / railings ==")
    fp = [[0.2, 0.2], [FP_W - 0.2, 0.2], [FP_W - 0.2, FP_D - 0.2], [0.2, FP_D - 0.2]]
    for name in L:
        li = int(name.split()[1])
        edit.add_covering(m, fp, "CEILING", 0.02, None, name); count["misc"] += 1     # suspended ceiling
        edit.add_covering(m, fp, "FLOORING", 0.02, None, name); count["misc"] += 1    # floor finish
        if 2 <= li <= N_ABOVE - 2:                        # residential floors: demising partitions + doors
            parts = [([12.5, 0], [12.5, FP_D]), ([21.5, 0], [21.5, FP_D]),            # W/E demising walls
                     ([0, 7], [12.5, 7]), ([0, 15], [12.5, 15]),                       # west apt separations
                     ([21.5, 7], [FP_W, 7]), ([21.5, 15], [FP_W, 15])]                 # east apt separations
            for a, b in parts:
                w = edit.add_wall(m, a, b, 3.0, 0.12, name); count["misc"] += 1
                edit.set_element_pset(m, w, "Pset_WallCommon", "IsExternal", False, "bool")
                # unit demising walls are 1-hr fire partitions (dwelling-unit separation, IBC 708/420)
                edit.set_element_pset(m, w, "Pset_WallCommon", "FireRating", "1 HR", "string")
                try:                                       # a unit entry door mid-partition
                    edit.add_opening(m, w, 0.9, 2.1, 0.0, "door", name,
                                     position=[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]); count["misc"] += 1
                except Exception:  # noqa: BLE001
                    pass
    # railings at the top amenity terrace edges
    for a, b in [([0, 0], [FP_W, 0]), ([FP_W, 0], [FP_W, FP_D]), ([FP_W, FP_D], [0, FP_D]), ([0, FP_D], [0, 0])]:
        try:
            edit.add_railing(m, a, b, 1.1, f"Level {N_ABOVE}"); count["misc"] += 1
        except Exception:  # noqa: BLE001
            pass

    # ---- ROOF ----
    print("== roof ==")
    roof_pts = [[0, 0], [FP_W, 0], [FP_W, FP_D], [0, FP_D]]
    edit.add_slab(m, roof_pts, 0.3, f"Level {N_ABOVE}"); count["struct"] += 1        # structural roof deck
    # roof assembly (IfcRoof: membrane/insulation over the deck) — the weatherproofing envelope element
    try:
        edit.RECIPES["add_roof"](m, {"points": roof_pts, "thickness": 0.15, "storey": f"Level {N_ABOVE}"})
        count["misc"] += 1
    except Exception as e:  # noqa: BLE001
        print("   roof-assembly skip:", e)
    for a, b in [([0, 0], [FP_W, 0]), ([FP_W, 0], [FP_W, FP_D]), ([FP_W, FP_D], [0, FP_D]), ([0, FP_D], [0, 0])]:
        edit.add_wall(m, a, b, 1.1, 0.2, f"Level {N_ABOVE}"); count["misc"] += 1   # parapet
    # rooftop cooling tower
    try:
        edit.add_mep_terminal(m, "IfcCoolingTower", [17, 11], 3, 3, 2.5, None, f"Level {N_ABOVE}", "Condenser Water", "hvac"); count["mep"] += 1
    except Exception:  # noqa: BLE001
        pass

    # ---- amenity furniture (a few) ----
    for cat, pt in [("sofa", [3, 3]), ("table", [8, 3]), ("chair", [10, 3])]:
        try:
            edit.place_content(m, cat, pt, name=f"Amenity {cat}", storey=f"Level {N_ABOVE}"); count["misc"] += 1
        except Exception:  # noqa: BLE001
            pass

    m.write(OUT)
    dt = time.time() - t0
    total = len(list(m.by_type("IfcElement"))) + len(list(m.by_type("IfcSpace")))
    print(f"\n== DONE in {dt:.0f}s ==")
    print(f"   file: {OUT}  ({os.path.getsize(OUT)/1e6:.1f} MB)")
    print(f"   authored: {count}")
    print(f"   IfcElement + IfcSpace total: {total}")
    print(f"   columns={len(m.by_type('IfcColumn'))} walls={len(m.by_type('IfcWall'))} "
          f"slabs={len(m.by_type('IfcSlab'))} beams={len(m.by_type('IfcBeam'))} "
          f"windows={len(m.by_type('IfcWindow'))} spaces={len(m.by_type('IfcSpace'))} "
          f"pipes={len(m.by_type('IfcPipeSegment'))} footings={len(m.by_type('IfcFooting'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
