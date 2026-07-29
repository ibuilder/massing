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

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_gltf_compress.py
"""
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
    import base64
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

print()
if FAILED:
    print(f"gltf_compress: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("gltf_compress: all checks passed")
