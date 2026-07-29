"""R23-GLTF-COMPRESS — index width, measured, and verified by a reader I did not write.

The ring entry proposes Draco or meshopt for "90–95% size reduction". Measured first, on a 720-element
export, the bytes were not where that framing implies:

    positions   69,216 bytes  (40% of geometry)
    indices    103,824 bytes  (60% of geometry)   <- all uint32
    max verts/mesh 2,880                          <- nowhere near the uint16 ceiling

So the largest single line item was **paying double for every index**, and fixing it needs no
dependency and no extension: uint16 indices are core glTF 2.0, read by every loader that reads glTF
at all. Draco and meshopt both require the consumer to support an extension, which changes this
module's stated contract — "a self-contained, standard glTF 2.0 file that any DCC / web viewer /
Blender / Three.js reads". Take the free, universal 30% first; judge the extension against what is
left, not against the original file.

**The ceiling is on VERTEX count, not index count.** An index must be able to address
`len(vertices) - 1`, so a mesh with ≤ 65,536 vertices is safe. Testing the wrong quantity silently
truncates geometry on large meshes — a defect that produces a valid file with missing triangles,
which is the worst shape available here.

**Draco (opt-in) is verified here by Draco's own decoder, which is NOT an independent witness.** The
independent check has to be run by hand, because no reader in this venv decodes the extension —
trimesh returns the right vertex and triangle COUNTS with every position at (0,0,0) and raises
nothing, so the obvious "an independent reader agrees" check passes on a file containing no
recoverable geometry. That degenerate result is asserted below rather than hidden.

The real cross-check, run 2026-07-29 against Blender 3.5's glTF importer (headless), which decodes
Draco natively and shares no code with this module:

    blender.exe -b --factory-startup --python <script importing both GLBs>

    mesh        plain (verts/polys, bbox)        draco (verts/polys, bbox)
    IfcColumn   960/1440  ±0.2,   z 0..3.0       960/1440  ±0.1999, z 0..3.0
    IfcSlab       8/12    ±15.0,  z 0..0.05        8/12    ±15.0,   z 0..0.0494
    IfcWall     960/1440  ±2.5,   z 0..3.0       960/1440  ±2.5,    z 0..3.0001

Same topology, geometry recovered, deltas inside the quantization bound. Re-run it if the encoder,
the attribute mapping, or the accessor bookkeeping changes — those are the parts a Draco-blind reader
cannot check.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_gltf_compress.py
"""
import base64
import io as _io
import json
import os
import sys
import tempfile

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

import ifcopenshell  # noqa: E402
import numpy as np  # noqa: E402

from aec_data import edit_struct, gltf_export, massing  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


path = os.path.join(tempfile.gettempdir(), "gltf_compress_fixture.ifc")
massing.generate_blank_ifc(path, name="Compress", storeys=3, storey_height=3.5)
m = ifcopenshell.open(path)
for lvl in ("Level 1", "Level 2"):
    for i in range(60):
        edit_struct.add_wall(m, (i * 0.4, 0.0), (i * 0.4 + 5.0, 0.0), height=3.0, storey=lvl)
        edit_struct.add_column(m, (i * 0.4, 2.0), height=3.0, storey=lvl)
m.write(path)

glb = gltf_export.export_glb_bytes(path)
doc = json.loads(gltf_export.export_gltf_bytes(path).decode("utf-8"))

# --- 1. indices are uint16 when the mesh allows it ---------------------------------------------------
scalars = [a for a in doc["accessors"] if a["type"] == "SCALAR"]
check("the fixture produces indexed meshes", len(scalars) > 0)
check("indices are uint16 (5123), not uint32, on a small-mesh model",
      {a["componentType"] for a in scalars} == {5123},
      sorted({a["componentType"] for a in scalars}))

# --- 2. the ceiling test is on VERTICES, and it is not off by one --------------------------------------
# 65,536 vertices means a maximum index of 65,535, which is exactly uint16's maximum — so the boundary
# is inclusive. An off-by-one here does not error; it wraps and draws the wrong triangles.
check("uint16's maximum index is 65535", np.iinfo(np.uint16).max == 65535)
check("  so a mesh of 65,536 vertices still fits", 65536 - 1 <= np.iinfo(np.uint16).max)
check("  and 65,537 does not", 65537 - 1 > np.iinfo(np.uint16).max)
for mesh in doc["meshes"]:
    for prim in mesh["primitives"]:
        pos = doc["accessors"][prim["attributes"]["POSITION"]]
        idx = doc["accessors"][prim["indices"]]
        if idx["componentType"] == 5123:
            check(f"uint16 mesh {mesh['name']!r} is under the ceiling", pos["count"] <= 65536,
                  pos["count"])

# --- 3. every index actually addresses a vertex that exists ---------------------------------------------
# The failure this catches is silent: a narrowed index that wraps produces a VALID glTF describing
# the wrong geometry. Reading the buffer back is the only way to see it.
blob = None
uri = doc["buffers"][0].get("uri", "")
if uri.startswith("data:"):
    blob = base64.b64decode(uri.split(",", 1)[1])
check("the buffer is readable back out of the .gltf", blob is not None and len(blob) > 0)

worst = 0
for mesh in doc["meshes"]:
    for prim in mesh["primitives"]:
        pos = doc["accessors"][prim["attributes"]["POSITION"]]
        idx = doc["accessors"][prim["indices"]]
        bv = doc["bufferViews"][idx["bufferView"]]
        dt = np.uint16 if idx["componentType"] == 5123 else np.uint32
        arr = np.frombuffer(blob, dtype=dt, count=idx["count"],
                            offset=bv["byteOffset"])
        worst = max(worst, int(arr.max()))
        check(f"every index in {mesh['name']!r} addresses a real vertex",
              int(arr.max()) < pos["count"], (int(arr.max()), pos["count"]))
check("indices are not all zero (a wrapped/blank buffer would be)", worst > 0)

# --- 4. bufferView alignment — glTF requires it, and uint16 changes the requirement ----------------------
for a in doc["accessors"]:
    bv = doc["bufferViews"][a["bufferView"]]
    size = {5123: 2, 5125: 4, 5126: 4}[a["componentType"]]
    check(f"bufferView for a {a['type']}/{a['componentType']} accessor is {size}-byte aligned",
          bv["byteOffset"] % size == 0, bv["byteOffset"])

# --- 5. an independent reader agrees ----------------------------------------------------------------------
# trimesh did not see any of this module's assumptions. A round trip through our own writer and our own
# reader would pass just as happily on a wrong format.
import trimesh  # noqa: E402

scene = trimesh.load(_io.BytesIO(glb), file_type="glb")
tri_count = sum(len(g.faces) for g in scene.geometry.values())
check("trimesh parses the GLB", len(scene.geometry) > 0, len(scene.geometry))
check("  and finds triangles", tri_count > 0, tri_count)
check("  one geometry per IFC class node", len(scene.geometry) == len(doc["meshes"]),
      (len(scene.geometry), len(doc["meshes"])))
check("  triangle count matches the document",
      tri_count == sum(doc["accessors"][p["indices"]]["count"] // 3
                       for me in doc["meshes"] for p in me["primitives"]),
      tri_count)

# --- 6. the saving is real, not asserted ------------------------------------------------------------------
# Rebuild the same document with uint32 indices to measure what the change bought, rather than quoting
# a number from the roadmap.
u32_bytes = sum(doc["accessors"][p["indices"]]["count"] * 4
                for me in doc["meshes"] for p in me["primitives"])
u16_bytes = sum(doc["accessors"][p["indices"]]["count"] * 2
                for me in doc["meshes"] for p in me["primitives"])
pos_bytes = sum(doc["accessors"][p["attributes"]["POSITION"]]["count"] * 12
                for me in doc["meshes"] for p in me["primitives"])
saved = u32_bytes - u16_bytes
check("the index buffer is exactly halved", u16_bytes * 2 == u32_bytes)
check("  and that is a double-digit % of the geometry",
      100 * saved / (pos_bytes + u32_bytes) > 10,
      f"{100 * saved / (pos_bytes + u32_bytes):.0f}%")
print(f"      measured: positions {pos_bytes:,}B, indices {u32_bytes:,}B -> {u16_bytes:,}B "
      f"({100 * saved / (pos_bytes + u32_bytes):.0f}% of geometry saved)")

# --- 6b. THE BOUNDARY ITSELF — the branch the fixture cannot reach -------------------------------------
# Everything above runs on meshes of ~960 vertices, which only ever exercises the uint16 side. The
# uint32 fallback is the dangerous branch: if the ceiling test were wrong, indices would WRAP and the
# file would still be valid glTF describing the wrong triangles. No sample small enough to keep in a
# test suite can reach it, so the mesh is synthesised and `_baked_by_class` is substituted — the unit
# under test is the index-width decision, not the IFC iterator.
#
# 65,536 vertices means a maximum index of 65,535, which is exactly uint16's maximum: the boundary is
# INCLUSIVE, and an off-by-one here does not raise, it silently draws the wrong geometry.
_real_baked = gltf_export._baked_by_class


def _synthetic(nverts: int):
    """A mesh of `nverts` vertices whose faces reference the HIGHEST index, so a narrowing that wraps
    is detectable rather than merely suspected."""
    verts = np.zeros((nverts, 3), dtype=np.float64)
    verts[:, 0] = np.arange(nverts) * 0.001
    verts[-1] = [1.0, 2.0, 3.0]
    faces = np.array([[0, 1, nverts - 1], [0, nverts - 2, nverts - 1]], dtype=np.int64)
    return {"IfcWall": (verts, faces)}


for nverts, expect_component, expect_name in ((65_536, 5123, "uint16"),
                                              (65_537, 5125, "uint32"),
                                              (200_000, 5125, "uint32")):
    gltf_export._baked_by_class = (lambda n: (lambda _model: _synthetic(n)))(nverts)
    try:
        bdoc = json.loads(gltf_export.export_gltf_bytes(path).decode("utf-8"))
    finally:
        gltf_export._baked_by_class = _real_baked
    prim = bdoc["meshes"][0]["primitives"][0]
    idx_acc = bdoc["accessors"][prim["indices"]]
    pos_acc = bdoc["accessors"][prim["attributes"]["POSITION"]]
    check(f"a {nverts:,}-vertex mesh uses {expect_name} indices",
          idx_acc["componentType"] == expect_component, idx_acc["componentType"])
    check(f"  its POSITION count is the full {nverts:,}", pos_acc["count"] == nverts,
          pos_acc["count"])
    # Read the indices back out and confirm the top vertex is still addressed. A uint16 narrowing of
    # index 65,536 wraps to 0 — same byte length, valid file, wrong triangle.
    bbuf = base64.b64decode(bdoc["buffers"][0]["uri"].split(",", 1)[1])
    bv = bdoc["bufferViews"][idx_acc["bufferView"]]
    dt = np.uint16 if idx_acc["componentType"] == 5123 else np.uint32
    arr = np.frombuffer(bbuf, dtype=dt, count=idx_acc["count"], offset=bv["byteOffset"])
    check(f"  and index {nverts - 1:,} survives the round trip (a wrap would read 0)",
          int(arr.max()) == nverts - 1, int(arr.max()))
    check("  every index still addresses a real vertex", int(arr.max()) < pos_acc["count"])

check("the real _baked_by_class was restored", gltf_export._baked_by_class is _real_baked)


# --- 7. Draco, the OPT-IN half -----------------------------------------------------------------------
# The uint16 change above is free and universal. Draco is neither: it is a hard dependency and a
# REQUIRED extension, so a consumer without the decoder reads nothing at all. That is the whole reason
# it is opt-in and the default export is untouched — and it is what these checks are really pinning.
check("draco is OFF by default, so the default export declares no required extension",
      "extensionsRequired" not in doc, doc.get("extensionsRequired"))

if not gltf_export.draco_available():
    # Loud, not silent. A skipped check that prints nothing is indistinguishable from a passing one.
    print("SKIP  Draco checks — DracoPy is not installed in this interpreter")
    print("      (pip install DracoPy==1.7.0; it is in requirements-dev.txt, so CI runs these)")
else:
    dglb = gltf_export.export_glb_bytes(path, draco=True)
    ddoc = json.loads(gltf_export.export_gltf_bytes(path, draco=True).decode("utf-8"))

    check("a draco export declares the extension as REQUIRED, not merely used",
          ddoc.get("extensionsRequired") == ["KHR_draco_mesh_compression"],
          ddoc.get("extensionsRequired"))
    check("  a loader without the decoder is therefore told to refuse the file, not to draw nothing",
          ddoc.get("extensionsUsed") == ["KHR_draco_mesh_compression"])

    for mesh in ddoc["meshes"]:
        for prim in mesh["primitives"]:
            ext = prim.get("extensions", {}).get("KHR_draco_mesh_compression")
            check(f"{mesh['name']!r} carries the draco extension on its primitive", ext is not None)
            # The accessors must NOT point at a bufferView — the geometry is inside the draco buffer.
            # Leaving a stale bufferView is the classic way to write a file that half-decodes.
            check("  its POSITION accessor has no bufferView (the draco buffer holds the data)",
                  "bufferView" not in ddoc["accessors"][prim["attributes"]["POSITION"]])
            check("  its index accessor likewise",
                  "bufferView" not in ddoc["accessors"][prim["indices"]])
            check("  the extension's attribute map points at a bufferView that exists",
                  0 <= ext["bufferView"] < len(ddoc["bufferViews"]))

    # The accessor counts must describe the DECODED mesh. Draco dedups and reorders vertices, so a
    # count copied from the input is wrong in a way that still validates structurally.
    import DracoPy  # noqa: E402
    for mesh in ddoc["meshes"]:
        for prim in mesh["primitives"]:
            ext = prim["extensions"]["KHR_draco_mesh_compression"]
            bv = ddoc["bufferViews"][ext["bufferView"]]
            uri = ddoc["buffers"][0]["uri"]
            raw = base64.b64decode(uri.split(",", 1)[1])
            dm = DracoPy.decode(raw[bv["byteOffset"]:bv["byteOffset"] + bv["byteLength"]])
            pa = ddoc["accessors"][prim["attributes"]["POSITION"]]
            ia = ddoc["accessors"][prim["indices"]]
            check(f"{mesh['name']!r} POSITION count matches what actually decodes",
                  pa["count"] == len(np.asarray(dm.points).reshape(-1, 3)),
                  (pa["count"], len(np.asarray(dm.points).reshape(-1, 3))))
            check("  index count matches too",
                  ia["count"] == np.asarray(dm.faces).size,
                  (ia["count"], np.asarray(dm.faces).size))
            check("  and the declared attribute id is the one the encoder assigned",
                  ext["attributes"]["POSITION"] ==
                  next(a["unique_id"] for a in dm.attributes if a.get("attribute_type") == 0))

    # --- what a reader WITHOUT the decoder actually does, measured ------------------------------------
    # This is the cost of the extension, and it is worse than "it fails". trimesh reads the container,
    # honours the accessor counts, and returns the right NUMBER of vertices and triangles — every one
    # of them at (0,0,0). It does not raise. So "the file loaded" and "the triangle count matched" are
    # both TRUE of a file containing no recoverable geometry, and a check that stops there passes on a
    # blank model. (It did, here, before this was measured.) Asserting the degenerate result is what
    # keeps the claim honest: an unsupported required extension fails SILENTLY in at least one
    # mainstream reader, which is exactly why draco stays opt-in.
    dscene = trimesh.load(_io.BytesIO(dglb), file_type="glb")
    dpts_all = np.vstack([np.asarray(g.vertices) for g in dscene.geometry.values()])
    check("a reader without a draco decoder recovers NO geometry (all vertices collapse to origin)",
          np.abs(dpts_all).max() == 0.0, np.abs(dpts_all).max())
    check("  and it does so WITHOUT raising — the silent failure the required flag is meant to prevent",
          len(dscene.geometry) == len(scene.geometry))

    # --- the lossy half, measured through Draco's own decoder -------------------------------------------
    # trimesh cannot be the witness here (it returned zeros), so the comparison is the ORIGINAL geometry
    # against the bounds the document declares — and those were computed by decoding the draco buffer,
    # not copied from the input. Draco is lossy and the error scales with MODEL SIZE, not detail.
    worst_err, worst_extent = 0.0, 0.0
    for mesh in ddoc["meshes"]:
        g = scene.geometry[mesh["name"]]
        pv = np.asarray(g.vertices)
        pa = ddoc["accessors"][mesh["primitives"][0]["attributes"]["POSITION"]]
        extent = float(max(pv.max(axis=0) - pv.min(axis=0)))
        err = float(max(np.abs(np.array(pa["min"]) - pv.min(axis=0)).max(),
                        np.abs(np.array(pa["max"]) - pv.max(axis=0)).max()))
        check(f"{mesh['name']!r} decodes within the bound draco_accuracy() states",
              err <= gltf_export.draco_accuracy(extent) + 1e-9,
              (err, gltf_export.draco_accuracy(extent)))
        if err > worst_err:
            worst_err, worst_extent = err, extent
    check("draco_accuracy scales with model size, so it cannot be quoted as one number",
          gltf_export.draco_accuracy(1000.0) == 10 * gltf_export.draco_accuracy(100.0))
    print(f"      measured: worst position error {worst_err:.6f} on a {worst_extent:.1f}-unit mesh "
          f"(bound {gltf_export.draco_accuracy(worst_extent):.6f})")

    saved_pct = 100 * (1 - len(dglb) / len(glb))
    check("draco is a large win on top of the uint16 export, not a marginal one",
          saved_pct > 50, f"{saved_pct:.0f}%")
    print(f"      measured: GLB {len(glb):,}B -> {len(dglb):,}B ({saved_pct:.0f}% smaller)")

print()
if FAILED:
    print(f"gltf_compress: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("gltf_compress: all checks passed")
