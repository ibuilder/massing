"""Geometric LOD on the glTF export — a triangle budget that is a ceiling, not a target.

WHAT THIS IS, AND WHAT IT IS NOT
    `max_faces_per_class` decimates exported geometry by vertex clustering, so a consumer receives a
    budget rather than a model. It is **geometric** level of DETAIL.

    It is not, and must not be confused with, `aec_api/lod.py` — which is level of DEVELOPMENT
    (LOD 100-500, BIM maturity inferred from LOIN facet completeness). Searching this codebase for
    "LOD" returns the other one first and answers a different question confidently. That collision is
    the reason this file says so twice.

    It also does **not** make the viewer faster. Our viewer streams Fragments, and there is no
    Fragments *writer* here to encode a decimated tier into — only an IFC to Fragments converter. So
    this lands where meshes are genuinely produced: the glTF interchange path. Claiming a first-paint
    win would be inventing a result the architecture cannot currently deliver.

WHAT IS ASSERTED
    - A budget actually reduces triangles, and the export still parses as glTF.
    - Under-budget geometry is returned UNTOUCHED. "A budget is a ceiling, not a target" is the whole
      contract; silently degrading a small mesh to hit a number would lose fidelity for nothing.
    - Decimation never empties a class. Deleting a whole discipline from an export is a far worse
      failure than a coarse one, and it would look like a successful export.
    - The default is OFF, so no existing caller changes behaviour.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


from aec_data import edit, gltf_export, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

FIX = os.path.join(tempfile.gettempdir(), "_gltf_lod_test.ifc")
massing.generate_blank_ifc(FIX, name="LOD Test", storeys=1, storey_height=4.0, ground_size=40.0)
m = open_model(FIX)
st = m.by_type("IfcBuildingStorey")[0].Name
for i in range(10):
    edit.add_wall(m, [0, i * 3.0], [20, i * 3.0], 3.0, 0.3, st)
m.write(FIX)
model = open_model(FIX)


def tri_counts(doc):
    """Triangles per mesh, read out of the document rather than from what we asked for."""
    acc = doc.get("accessors", [])
    out = {}
    for mesh in doc.get("meshes", []):
        n = 0
        for prim in mesh.get("primitives", []):
            idx = prim.get("indices")
            if idx is not None and idx < len(acc):
                n += acc[idx].get("count", 0) // 3
        out[mesh.get("name", "?")] = n
    return out


# ---------------------------------------------------------------- baseline: the default is OFF
full = gltf_export.export_gltf(model, name="full")
base = tri_counts(full)
check("the export produced geometry", sum(base.values()) > 0,
      f"{sum(base.values())} triangles across {len(base)} class(es)")
check("the export is serialisable glTF", bool(json.dumps(full)) and full.get("asset", {}).get("version") == "2.0",
      full.get("asset", {}).get("version"))

# ---------------------------------------------------------------- a budget reduces triangles
BUDGET = 20
small = gltf_export.export_gltf(model, name="small", max_faces_per_class=BUDGET)
cut = tri_counts(small)
check("a budget reduces the triangle count",
      sum(cut.values()) < sum(base.values()),
      f"{sum(base.values())} -> {sum(cut.values())} (budget {BUDGET}/class)")
check("the decimated export is still valid glTF",
      small.get("asset", {}).get("version") == "2.0" and bool(small.get("meshes")))

# ---------------------------------------------------------------- it never empties a class
lost = sorted(k for k in base if cut.get(k, 0) == 0 and base[k] > 0)
check("decimation never empties a class", not lost,
      f"emptied: {lost}" if lost else f"{len(base)} class(es) all still present")
check("the decimated export keeps every class the full one had",
      set(cut) == set(base), f"{sorted(set(base) - set(cut))}" if set(cut) != set(base) else "same classes")

# ---------------------------------------------------------------- a ceiling, not a target
huge = gltf_export.export_gltf(model, name="huge", max_faces_per_class=10_000_000)
untouched = tri_counts(huge)
check("an unreachable budget leaves the geometry untouched",
      untouched == base,
      "same counts" if untouched == base else f"{base} -> {untouched}")

# ---------------------------------------------------------------- default off
check("decimation is OFF by default (no existing caller changes behaviour)",
      tri_counts(gltf_export.export_gltf(model, name="d")) == base)

# ---------------------------------------------------------------- the two LODs are different things
# A guard against the collision this module's docstring warns about: if someone ever "unifies" these,
# this fails rather than letting a maturity score start decimating meshes.
from aec_api import lod as lod_development  # noqa: E402

check("aec_api.lod is level of DEVELOPMENT, not detail",
      "LOD 100" in getattr(lod_development, "LOD_BANDS", []),
      str(getattr(lod_development, "LOD_BANDS", [])[:3]))
check("geometric decimation lives in the vendored geometry package, not in aec_api.lod",
      not hasattr(lod_development, "cluster_decimate")
      and not hasattr(lod_development, "decimate_to_budget"))

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_gltf_lod OK")
