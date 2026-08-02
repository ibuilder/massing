"""R23-STOREY-LOD — the proxy generator, and the ways a coarse stand-in goes quietly wrong.

**The fixture is GENERATED, never read from `samples/`.** The first version of this suite read
`samples/school_str.ifc`, which is untracked — three files in `samples/` are in the archive and twenty
are on disk — so it passed here and failed on every other machine, and it turned main red. `git
ls-files` before a test reads a path. It went honestly red rather than vacuously green only because
it asserted the fixture existed, which is the one thing the original got right.

The assertions are about the four ways a proxy misleads rather than merely underperforms:

1. **an invisible proxy.** `_rect_profile`'s docstring warns that web-ifc silently skips an element
   whose profile has no Position — it renders nothing, reports nothing, and the "LOD" is simply
   missing geometry. A proxy nobody can see is the same as no proxy, and nothing would say so;
2. **a proxy that does not declare itself.** A coarse box mistaken for authored geometry gets
   measured, scheduled and priced. It carries a name prefix AND a pset, so the fact survives whichever
   one a reader happens to look at;
3. **an empty export that reads as success** — a written file with no content is worse than a refusal;
4. **structure quietly replaced by boxes**, which a viewer cannot signal and a user cannot see through.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_lod_proxy.py
"""
import os
import sys
import tempfile

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

import ifcopenshell  # noqa: E402
import ifcopenshell.geom as geom  # noqa: E402
import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit, lod, massing  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- the fixture, stated in full so every asserted quantity is derivable from this block -------------
# 2 storeys. Per storey: 4 ducts (IfcFlowSegment — proxyable) plus 1 slab and 2 walls (structure,
# which must NOT be proxied). So 8 proxyable elements across 2 storeys, and a structural population
# the proxy has to leave alone. mkdtemp rather than mktemp: mktemp returns a name without creating it
# and leaves a create-after-name race (py/insecure-temporary-file).
DUCTS_PER_STOREY = 4
WORK = tempfile.mkdtemp(prefix="lod_proxy_fixture_")
SRC = os.path.join(WORK, "fixture.ifc")
massing.generate_blank_ifc(SRC, name="LODFixture", storeys=2, storey_height=3.0)
_m = ifcopenshell.open(SRC)
_storeys = [s.Name for s in _m.by_type("IfcBuildingStorey")]
for _st in _storeys:
    edit.RECIPES["add_slab"](_m, {"points": [[0, 0], [10, 0], [10, 8], [0, 8]],
                                  "thickness": 0.2, "storey": _st})
    edit.RECIPES["add_wall"](_m, {"start": [0, 0], "end": [10, 0], "height": 3.0, "storey": _st})
    edit.RECIPES["add_wall"](_m, {"start": [0, 0], "end": [0, 8], "height": 3.0, "storey": _st})
    for _i in range(DUCTS_PER_STOREY):
        edit.RECIPES["add_duct"](_m, {"start": [1 + _i, 1], "end": [1 + _i, 6], "storey": _st})
_m.write(SRC)

EXPECTED_PROXYABLE = DUCTS_PER_STOREY * len(_storeys)          # 8
model = ifcopenshell.open(SRC)
check("the generated fixture carries the proxyable class",
      len(model.by_type("IfcFlowSegment")) == EXPECTED_PROXYABLE,
      f"{len(model.by_type('IfcFlowSegment'))} of {EXPECTED_PROXYABLE}")
# 3 slabs, not 2: generate_blank_ifc already lays a ground slab, so the two authored here make three.
# Stated rather than asserted loosely, so the number stays derivable from the fixture block above.
check("  and structure the proxy must leave alone",
      len(model.by_type("IfcSlab")) == 3 and len(model.by_type("IfcWall")) >= 4,
      f"{len(model.by_type('IfcSlab'))} slabs, {len(model.by_type('IfcWall'))} walls")

# --- 1. a real proxy from that model ------------------------------------------------------------------
out = os.path.join(WORK, "proxy.ifc")
rep = lod.build_storey_proxy(model, out)

check("a proxy is written", rep["written"] is True, rep.get("reason"))
check("  it replaces every proxyable element", rep["elements_replaced"] == EXPECTED_PROXYABLE,
      rep["elements_replaced"])
check("  one box per storey, not one per element", rep["storeys_proxied"] == 2, rep["storeys_proxied"])

proxy = ifcopenshell.open(out)
boxes = proxy.by_type("IfcBuildingElementProxy")
check("the proxy model holds exactly the storey boxes", len(boxes) == 2, len(boxes))

# THE INVISIBLE-PROXY TRAP — the failure mode with no symptom.
settings = geom.settings()
tris = 0
for b in boxes:
    # BIND the shape. `len(create_shape(...).geometry.faces)` chains off a temporary whose buffer is
    # released before `.faces` is read and returns 0 — which here reads exactly like the invisible
    # proxy this assertion exists to catch. It cost a false FAIL on working code, and would have cost
    # a false PASS with the polarity reversed. Same family as a detached ArrayBuffer reporting zero.
    shape = geom.create_shape(settings, b)
    tris += len(shape.geometry.faces) // 3
check("THE PROXY HAS GEOMETRY — a null profile Position renders it invisible and reports nothing",
      tris > 0, f"{tris} triangles: web-ifc would skip these silently")
check("  and it is coarse — a box is 12 triangles", tris == 12 * len(boxes), tris)

# DECLARES ITSELF, twice over.
check("every proxy is NAMED as a proxy", all(b.Name.startswith(lod.PROXY_NAME_PREFIX) for b in boxes),
      [b.Name for b in boxes])
ps = ue.get_psets(boxes[0]).get(lod.PROXY_PSET) or {}
check("  and carries the AEC_LOD pset, so the fact survives either reader", ps.get("IsProxy") is True, ps)
# The CONCRETE class is recorded — an authored duct is an IfcDuctSegment, which matches the
# IfcFlowSegment policy entry by inheritance. Recording the supertype would hide what was replaced.
check("  naming the concrete classes it stands in for",
      ps.get("ReplacesClasses") == "IfcDuctSegment", ps)
check("  and how many elements it replaced", int(ps.get("ReplacesElementCount", 0)) > 0, ps)
check("  with a note telling a downstream tool NOT to measure or price it",
      "do not measure" in (ps.get("Note") or ""), ps.get("Note"))

# STRUCTURE IS UNTOUCHED — the proxy model contains no stand-in for slabs or walls.
check("no slab or wall was replaced — structure is not in the default set",
      not proxy.by_type("IfcSlab") and not proxy.by_type("IfcWall"),
      f"{len(proxy.by_type('IfcSlab'))} slabs, {len(proxy.by_type('IfcWall'))} walls in the proxy")

check("each proxied storey reports its bounds, so the box can be checked",
      all("bbox" in r for r in rep["storeys"] if r["proxied"]), rep["storeys"])

# --- 2. nothing to proxy is a REFUSAL, not an empty file ------------------------------------------------
blank_dir = tempfile.mkdtemp(prefix="lod_blank_")
blank = os.path.join(blank_dir, "blank.ifc")
massing.generate_blank_ifc(blank, name="Empty", storeys=2, storey_height=3.5)
bm = ifcopenshell.open(blank)
out2 = os.path.join(blank_dir, "proxy_out.ifc")
r2 = lod.build_storey_proxy(bm, out2)
check("a model with no proxyable class writes NO file", r2["written"] is False, r2)
check("  and says so rather than exporting an empty model that looks successful",
      "successful export" in r2["reason"], r2["reason"])
check("  and no file was actually created", not os.path.exists(out2), out2)
check("  the status is no_geometry, not a clean zero",
      r2["status"] == lod.STATUS_NO_GEOMETRY, r2["status"])

r3 = lod.build_storey_proxy(model, os.path.join(WORK, "none.ifc"), classes=("IfcDoor",))
check("asking for a class the model lacks refuses rather than writing an empty proxy",
      r3["written"] is False, r3)

check("structure is not in the default proxy set",
      not (set(lod.STRUCTURAL_CLASSES) & set(lod.SMALL_PART_CLASSES)))
check("the proxy marker constants are exported so a reader can find them",
      lod.PROXY_PSET == "AEC_LOD" and lod.PROXY_NAME_PREFIX.startswith("LOD Proxy"))

# --- 3. THE ROUTES — because an engine nothing can call is the defect this repo keeps finding ---------
# `test_reachable` scans `aec_api` only, so it is structurally unable to see an orphan in `aec_data`.
# lod.py was imported by nothing but its own tests until these landed. Asserted over HTTP, because a
# route in a file is not a route.
os.environ["DATABASE_URL"] = "sqlite:///./test_lod_proxy_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_lod_proxy_route"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_lod_proxy_route.db"):
    os.remove("./test_lod_proxy_route.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as client:
    client.headers.update({"X-User": "lod@test"})
    pid = client.post("/projects", json={"name": "LOD"}).json()["id"]

    r = client.get(f"/projects/{pid}/model/lod/census")
    check("the census route 409s without a source model, rather than 500ing",
          r.status_code == 409, r.status_code)
    r = client.post(f"/projects/{pid}/model/lod/proxy", json={})
    check("  and so does the proxy route", r.status_code == 409, r.status_code)

    with SessionLocal() as db:
        proj = db.get(Project, pid)
        proj.source_ifc = os.path.abspath(SRC)
        db.commit()

    c = client.get(f"/projects/{pid}/model/lod/census").json()
    check("the census route answers over HTTP", c["status"] == lod.STATUS_OK, c.get("status"))
    check("  it reports the proxyable class it found",
          any(row["ifc_class"] == "IfcDuctSegment" and row["small_part"] for row in c["by_class"]),
          [row["ifc_class"] for row in c["by_class"]])
    check("  an uncapped census says its saving is complete, not a lower bound",
          c["plan"]["saving_is_lower_bound"] is False, c["plan"])

    capped = client.get(f"/projects/{pid}/model/lod/census?max_elements=2").json()
    check("  a CAPPED census marks its saving a lower bound, so a small number is not a verdict",
          capped["capped"] is True and capped["plan"]["saving_is_lower_bound"] is True, capped["plan"])

    pr = client.post(f"/projects/{pid}/model/lod/proxy", json={}).json()
    check("the proxy route stores an artefact", pr.get("stored") is True, pr.get("reason"))
    check("  replacing every proxyable element", pr["elements_replaced"] == EXPECTED_PROXYABLE,
          pr["elements_replaced"])
    check("  and keys it beside the model", str(pr.get("key", "")).endswith("model.lod.ifc"),
          pr.get("key"))

print()
if FAILED:
    print(f"lod_proxy: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("lod_proxy: all checks passed")
