"""BFAST / G3D / VIM reader (G2): container round-trip, G3D geometry extraction, VIM inspection.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_bfast.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

import numpy as np  # noqa: E402

from aec_data import bfast  # noqa: E402

# --- BFAST container round-trip -------------------------------------------------------------------
buffers = {"alpha": b"hello", "beta": bytes(range(50)), "gamma": b""}
blob = bfast.write_bfast(buffers)
assert blob[:8] and int.from_bytes(blob[:8], "little") == bfast.MAGIC, "magic header"
back = bfast.read_bfast(blob)
assert list(back) == ["alpha", "beta", "gamma"], back.keys()
assert back["alpha"] == b"hello" and back["beta"] == bytes(range(50)) and back["gamma"] == b"", "round-trip"
# garbage / too-small inputs raise cleanly
_rejected = False
try:
    bfast.read_bfast(b"nope")
except ValueError:
    _rejected = True
assert _rejected, "garbage input should raise ValueError"

# --- G3D geometry ---------------------------------------------------------------------------------
verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 2]], dtype=np.float32)
idx = np.array([0, 1, 2, 0, 1, 3], dtype=np.int32)
g3d = bfast.write_bfast({
    "g3d:vertex:position:0:float32:3": verts.tobytes(),
    "g3d:corner:index:0:int32:1": idx.tobytes(),
})
geo = bfast.g3d_geometry(bfast.read_bfast(g3d))
assert geo["is_g3d"] and geo["vertices"] == 4 and geo["triangles"] == 2, geo
assert geo["bbox"] == [[0.0, 0.0, 0.0], [1.0, 1.0, 2.0]], geo["bbox"]

# --- VIM inspection (a BFAST with header + nested geometry G3D) -----------------------------------
vim = bfast.write_bfast({
    "header": b"vim=1.0\ngenerator=UnitTest\nschema=IFC4\n",
    "geometry": g3d,
    "entities": b"(opaque entity table)",
})
info = bfast.vim_info(vim)
assert info["format"] == "VIM" and info["vim_version"] == "1.0", info
assert info["generator"] == "UnitTest" and info["schema"] == "IFC4", info
assert set(info["buffers"]) == {"header", "geometry", "entities"}, info["buffers"]
assert info["geometry"]["triangles"] == 2, info["geometry"]

print("BFAST OK - container write/read round-trips 3 named buffers (magic verified, garbage rejected); "
      "G3D geometry extracted (4 verts, 2 triangles, bbox); VIM inspection reads header (vim=1.0, "
      "schema IFC4), buffer inventory + nested geometry stats — pure-Python interop for .vim/.g3d")
