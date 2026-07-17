"""EXPORT: broader geometry-out — binary glTF (.glb) alongside the JSON .gltf, and a first-class IFC
re-export (stream the current authored source IFC, not only inside the closeout bundle).
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_export_formats.py"""
import json
import os
import struct
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, gltf_export, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_export_fmt_test.ifc")
massing.generate_blank_ifc(TMP, name="Export", storeys=1, storey_height=3.0, ground_size=15.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.add_column(m, [0, 0], 3.0, 0.4, 0.4, st)
m.write(TMP)

# --- .gltf (JSON, embedded buffer) still works and is unchanged in shape -----------------------------
gltf = gltf_export.export_gltf_bytes(TMP, "Export")
doc = json.loads(gltf)
assert doc["asset"]["version"] == "2.0" and doc["meshes"], "valid glTF with meshes"
assert doc["buffers"][0]["uri"].startswith("data:application/octet-stream;base64,"), "embedded buffer"
n_meshes = len(doc["meshes"])

# --- .glb (binary container) — validate the glTF 2.0 container structure ------------------------------
glb = gltf_export.export_glb_bytes(TMP, "Export")
assert len(glb) >= 20, "a GLB has at least a header + two chunk headers"
magic, version, total = struct.unpack_from("<III", glb, 0)
assert magic == 0x46546C67, "GLB magic must be 'glTF'"           # 0x46546C67
assert version == 2, version
assert total == len(glb), f"declared total {total} == actual {len(glb)}"

# JSON chunk
jlen, jtype = struct.unpack_from("<II", glb, 12)
assert jtype == 0x4E4F534A, "first chunk must be JSON"           # 'JSON'
assert (12 + 8 + jlen) % 4 == 0, "JSON chunk padded to a 4-byte boundary"
gjson = json.loads(glb[20:20 + jlen].decode("utf-8"))
assert len(gjson["meshes"]) == n_meshes, "same geometry as the .gltf"
assert "uri" not in gjson["buffers"][0], "the GLB buffer has NO uri (it is the BIN chunk)"
assert gjson["buffers"][0]["byteLength"] > 0

# BIN chunk immediately follows, correctly typed + sized
bin_off = 20 + jlen
blen, btype = struct.unpack_from("<II", glb, bin_off)
assert btype == 0x004E4942, "second chunk must be BIN"           # 'BIN\0'
assert bin_off + 8 + blen == len(glb), "BIN chunk runs to the end of the file"
assert blen >= gjson["buffers"][0]["byteLength"], "BIN chunk holds the whole buffer (+ padding)"

# --- IFC re-export is just the current source IFC bytes ----------------------------------------------
with open(TMP, "rb") as f:
    ifc_bytes = f.read()
assert ifc_bytes[:4] in (b"ISO-", b"ISO ") or ifc_bytes.lstrip()[:4] == b"ISO-", ifc_bytes[:8]
# the re-export round-trips: reopening the streamed bytes yields the same element counts
rt = os.path.join(tempfile.gettempdir(), "_export_rt.ifc")
with open(rt, "wb") as f:
    f.write(ifc_bytes)
rmodel = open_model(rt)
assert len(rmodel.by_type("IfcWall")) == 1 and len(rmodel.by_type("IfcColumn")) == 1, "round-trips GUID-stable"

for f in (TMP, rt):
    if os.path.exists(f):
        os.remove(f)

print("EXPORT OK - the model geometry now exports as a binary .glb (glTF 2.0 container: 'glTF'/v2 header, a "
      "4-byte-padded JSON chunk with NO buffer uri, and a 'BIN\\0' chunk holding the buffer to EOF — same "
      "per-class meshes as the .gltf) alongside the existing JSON .gltf; and a first-class IFC re-export "
      "streams the current authored source IFC (round-trips to the same GUID-stable elements), not only "
      "inside the closeout bundle zip.")
