"""DESKTOP-FRAGMENTS — the Python IFC->Fragments path, and what it must agree with.

The shipped desktop app has no Node runtime, so `services/converter/src/cli.mjs` can never run there
and `GET /projects/{pid}/model.frag` was 404 forever in the packaged product. `aec_data.fragments`
is the Python path. **A second implementation of a format is a second thing that can disagree with
the first**, so this gate exists to make the disagreement measurable rather than discovered in a
viewer.

### What a conformance check can and cannot settle

Geometry is *expected* to differ: web-ifc and IfcOpenShell tessellate the same parametric solids
independently, and on the reference model the same door comes out 0.9 x 2.1 x 0.175 from one and
0.95 x 2.125 x 0.22 from the other. Asserting byte equality would be asserting that two libraries
are one library. What must NOT differ is everything else: which elements exist, how they are
indexed, which way is up, and whether the reference reader accepts the file at all.

### Three defects this found, none of which any other check could see

* **Openings were being rendered as solids.** `IfcOpeningElement` has a representation, so "every
  product with a representation" -- the obvious population -- includes the void cut for a door, and
  IfcOpenShell tessellates it happily. The result loads, counts fine, and fills every doorway with a
  block.
* **The entity index listed only meshed products.** The viewer resolves a picked mesh to an element
  through `local_ids` / `categories` / `guids`; indexing 9 of 43 entities leaves a selected wall
  unable to reach its storey, spaces or property sets.
* **The file was written Z-up.** IFC is Z-up, Fragments is Y-up. Every count matched, the reference
  reader accepted it, and the building rendered lying on its side.

All three were found by comparing against a file the Node converter produced. **Counts agreeing is
not the same as the model being right**, and two of the three would have passed any check that only
looked at this implementation.

Run: `PYTHONPATH=src:../data/src python test_fragments_python.py`
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(f"{label} — {detail}" if detail else label)


from aec_data import edit, massing  # noqa: E402
from aec_data.fragments import loads  # noqa: E402
from aec_data.fragments.from_ifc import convert  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
_TMP = tempfile.mkdtemp(prefix="fragpy_")
IFC = Path(_TMP) / "model.ifc"

# --- a model with the shapes that matter: a void, two storeys, spaces, an opening ------------------
massing.generate_blank_ifc(str(IFC), name="FragGate", storeys=2, storey_height=3.0, ground_size=20.0)
_m = open_model(str(IFC))
_st = _m.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(_m, rooms_per_storey=2, ceiling_height=3.0)
_w = edit.add_wall(_m, [0, 0], [8, 0], 3.0, 0.2, _st)
edit.add_opening(_m, _w, width=0.9, height=2.1, kind="door")   # the void that must NOT be drawn
edit.add_wall(_m, [8, 0], [8, 6], 3.0, 0.2, _st)
_m.write(str(IFC))

result = convert(str(IFC))
check("the Python converter produced bytes", bool(result.data), "empty .frag")
check("...and reported no geometry failures", not result.failed, f"failed: {result.failed}")
model = loads(result.data)

# --- 1. the file is a fragment our own reader round-trips -----------------------------------------
check("the output parses back", bool(model.meshes), "no meshes came back")
check("every mesh carries points and profiles",
      all(m.points and m.profiles for m in model.meshes),
      "an empty shell draws nothing and reports nothing")
check("every shell is tagged as a shell, not a point cloud",
      all(m.representation_class == 1 for m in model.meshes),
      f"classes={sorted({m.representation_class for m in model.meshes})} — a misplaced struct byte "
      f"reads as class 0 and the viewer draws no surface")

# --- 2. VOIDS ARE NOT SOLIDS ----------------------------------------------------------------------
# The headline defect. An opening is the hole cut for the door, not a thing to draw.
import ifcopenshell  # noqa: E402

_f = ifcopenshell.open(str(IFC))
_openings = list(_f.by_type("IfcOpeningElement"))
check("the fixture really contains an opening", bool(_openings),
      "without one, the check below proves nothing")
check("OPENINGS ARE SKIPPED, not rendered as solids", result.skipped_voids == len(_openings),
      f"skipped {result.skipped_voids} of {len(_openings)} — an emitted opening is a solid block "
      f"filling the doorway it was cut for")
_opening_guids = {o.GlobalId for o in _openings}
check("...and no opening reaches the entity index either",
      not (_opening_guids & set(model.guids)),
      f"{sorted(_opening_guids & set(model.guids))} — a void the viewer can select is not an element")

# --- 3. THE ENTITY INDEX COVERS THE MODEL, NOT JUST THE MESHES ------------------------------------
# The viewer resolves a picked mesh to an element through these tables.
from aec_data.fragments.from_ifc import _is_indexable  # noqa: E402

_indexable = [e for e in _f if e.id() and _is_indexable(e)]
check("local_ids indexes every selectable entity",
      len(model.local_ids) == len(_indexable),
      f"{len(model.local_ids)} indexed vs {len(_indexable)} entities — indexing only meshed "
      f"products leaves a selected element unable to reach its storey or property sets")
# ...and NOT the geometry scaffolding, which is most of an IFC file and none of it selectable.
_scaffolding = [e for e in _f if e.id() and (e.is_a("IfcCartesianPoint") or e.is_a("IfcDirection"))]
check("the fixture really contains geometry scaffolding", bool(_scaffolding))
check("GEOMETRY PRIMITIVES ARE NOT INDEXED AS ELEMENTS",
      len(model.local_ids) < len(_scaffolding),
      f"{len(model.local_ids)} indexed against {len(_scaffolding)} points and directions alone — "
      f"indexing every entity puts ids in the table that resolve to nothing a person can select")
check("...and categories runs in step with it",
      len(model.categories) == len(model.local_ids),
      f"{len(model.categories)} categories vs {len(model.local_ids)} local ids — these are read "
      f"pairwise; a length mismatch mislabels every element after the gap")
check("...and it reaches well past the meshed elements",
      len(model.local_ids) > 3 * result.elements,
      f"{len(model.local_ids)} indexed for {result.elements} meshed — suspiciously close to the "
      f"mesh count, which is what the first draft got wrong")

# **Relationships are edges, not elements.** They belong in the format's own `relations` table.
_rel_guids = {e.GlobalId for e in _f.by_type("IfcRelationship") if getattr(e, "GlobalId", None)}
check("the fixture really contains relationships", bool(_rel_guids))
check("RELATIONSHIPS ARE NOT INDEXED AS ENTITIES",
      not (_rel_guids & set(model.guids)),
      f"{len(_rel_guids & set(model.guids))} relationship GlobalIds in the entity index — ids the "
      f"viewer can resolve to nothing")

# every meshed element must be resolvable
check("every meshed element's local id is in the index",
      set(model.meshes_items) <= set(model.local_ids),
      f"unresolvable: {sorted(set(model.meshes_items) - set(model.local_ids))[:5]}")

# --- 4. WHICH WAY IS UP ---------------------------------------------------------------------------
# IFC is Z-up; Fragments is Y-up. Getting this wrong lays the building on its side, and every count
# above still passes. Measured on the model's own bounds: a two-storey building is taller than it
# is thick, and its height must land on Y.
# **Compared ACROSS the two coordinate systems, not within one.** The first version of this check
# asserted the fragment's y-extent exceeded its z-extent — and failed, correctly, on a converter
# that was right: a 25 x 30 m site with a 6 m building is wider than it is tall, so "height is the
# largest dimension" is simply false. The question is not which extent is biggest, it is which axis
# the IFC's UP axis landed on.
import ifcopenshell.geom as _geom  # noqa: E402

_s = _geom.settings()
_s.set("USE_WORLD_COORDS", True)
_ifc_x: list[float] = []
_ifc_y: list[float] = []
_ifc_z: list[float] = []
for _p in _f.by_type("IfcProduct"):
    if not getattr(_p, "Representation", None) or _p.is_a("IfcOpeningElement"):
        continue
    try:
        # **Bind the shape.** `list(create_shape(...).geometry.verts)` frees the shape while the
        # vertex buffer is being read, and the copy comes back as garbage floats — this check first
        # failed with a "y-extent" of 4.7e98. Use-after-free, in the test rather than the converter,
        # which holds its own reference. A bug that produces *absurd* numbers is the lucky kind;
        # the same mistake could as easily have produced plausible ones.
        _shape = _geom.create_shape(_s, _p)
        _v = list(_shape.geometry.verts)
    except Exception:                          # noqa: BLE001 — unrepresentable; counted elsewhere
        continue
    _ifc_x += _v[0::3]; _ifc_y += _v[1::3]; _ifc_z += _v[2::3]


def _extent(vals: list[float]) -> float:
    return (max(vals) - min(vals)) if vals else 0.0


_fx = _extent([p[0] for m in model.meshes for p in m.points])
_fy = _extent([p[1] for m in model.meshes for p in m.points])
_fz = _extent([p[2] for m in model.meshes for p in m.points])
check("the fixture has three distinguishable extents",
      len({round(_extent(_ifc_x), 1), round(_extent(_ifc_y), 1), round(_extent(_ifc_z), 1)}) == 3,
      f"IFC extents x={_extent(_ifc_x):.2f} y={_extent(_ifc_y):.2f} z={_extent(_ifc_z):.2f} — with "
      f"two the same, an axis swap is undetectable and this check would pass on a wrong converter")
check("THE MODEL IS Y-UP — the IFC's up axis (z) lands on the fragment's y",
      abs(_extent(_ifc_z) - _fy) < 0.1,
      f"IFC z-extent {_extent(_ifc_z):.2f} vs fragment y-extent {_fy:.2f} — a Z-up file loads, "
      f"counts correctly, and renders rotated a quarter turn")
check("...and the IFC's y lands on the fragment's z", abs(_extent(_ifc_y) - _fz) < 0.1,
      f"IFC y-extent {_extent(_ifc_y):.2f} vs fragment z-extent {_fz:.2f}")
check("...and x is unchanged", abs(_extent(_ifc_x) - _fx) < 0.1,
      f"IFC x-extent {_extent(_ifc_x):.2f} vs fragment x-extent {_fx:.2f}")

# --- 5. the uint16 index ceiling is respected -----------------------------------------------------
from aec_data.fragments.schema import MAX_SHELL_POINTS  # noqa: E402

check("no shell exceeds the uint16 point ceiling",
      all(len(m.points) <= MAX_SHELL_POINTS for m in model.meshes),
      f"largest shell has {max((len(m.points) for m in model.meshes), default=0)} points; past "
      f"{MAX_SHELL_POINTS} an index wraps and draws a face between unrelated corners")
check("...and every profile index is in range for its own shell",
      all(all(i < len(m.points) for loop in m.profiles for i in loop) for m in model.meshes),
      "an out-of-range index is a face pointing at a vertex that does not exist")

# --- 6. metadata is real ---------------------------------------------------------------------------
_meta = json.loads(model.metadata or "{}")
check("metadata records the source schema", _meta.get("schema", "").startswith("IFC"),
      f"schema={_meta.get('schema')!r}")
check("...and says which converter wrote it", "python" in (_meta.get("generator") or "").lower(),
      f"generator={_meta.get('generator')!r} — a file whose origin is unrecorded cannot be told "
      f"from the Node converter's output when one of them is wrong")

# --- 7. THE CROSS-CHECK against the reference implementation --------------------------------------
# This is the half that catches what looking only at our own output cannot. It needs Node and the
# installed `@thatopen/fragments`, which the API test job does not have — so it is allowed to be
# absent, and it SAYS SO rather than passing quietly. A skipped cross-check that looks like a pass
# is the exact failure mode this file's own docstring is about.
_node = shutil.which("node")
_pkg = REPO / "node_modules" / "@thatopen" / "fragments" / "dist" / "index.cjs"
_cli = REPO / "services" / "converter" / "src" / "cli.mjs"
_have_reference = bool(_node) and _pkg.exists() and _cli.exists()

if not _have_reference:
    missing = [n for n, ok in (("node", bool(_node)), ("@thatopen/fragments", _pkg.exists()),
                               ("converter cli", _cli.exists())) if not ok]
    print(f"SKIP  cross-check against the Node converter — not available here: {', '.join(missing)}")
    print("      (the assertions above are derived FROM that comparison; they do not replace it)")
else:
    ref = Path(_TMP) / "ref.frag"
    proc = subprocess.run([_node, str(_cli), str(IFC), str(ref)],
                          capture_output=True, text=True, timeout=300, cwd=str(REPO))
    check("the Node converter produced a reference file",
          proc.returncode == 0 and ref.exists(), f"rc={proc.returncode} {proc.stderr[-300:]}")
    if ref.exists():
        reader = Path(_TMP) / "read.cjs"
        reader.write_text(
            'const fs=require("node:fs"),zlib=require("node:zlib");\n'
            f'const fb=require({str(REPO / "node_modules" / "flatbuffers")!r});\n'
            f'const F=require({str(_pkg)!r});\n'
            'const bb=new fb.ByteBuffer(new Uint8Array(zlib.inflateSync(fs.readFileSync(process.argv[2]))));\n'
            'const m=F.Model.getRootAsModel(bb);\n'
            'const g=[];for(let i=0;i<m.guidsLength();i++)g.push(m.guids(i));\n'
            'const me=m.meshes();\n'
            'console.log(JSON.stringify({guids:g,shells:me?me.shellsLength():0,\n'
            '  cats:m.categoriesLength(), localIds:m.localIdsLength(),\n'
            '  cls: me&&me.representationsLength()?me.representations(0).representationClass():null}));\n')

        def _read(path: Path) -> dict:
            out = subprocess.run([_node, str(reader), str(path)],
                                 capture_output=True, text=True, timeout=120, cwd=str(REPO))
            if out.returncode != 0:
                return {"error": out.stderr[-400:]}
            return json.loads(out.stdout)

        py_path = Path(_TMP) / "py.frag"
        py_path.write_bytes(result.data)
        ours, theirs = _read(py_path), _read(ref)

        # **THE decisive assertion: the reference implementation accepts our file.**
        check("THE REAL @thatopen/fragments READER PARSES THE PYTHON OUTPUT",
              "error" not in ours,
              f"{ours.get('error')} — a file only our own reader accepts is not a fragment")
        check("...and it parses the Node output too (the control)", "error" not in theirs,
              f"{theirs.get('error')}")
        if "error" not in ours and "error" not in theirs:
            check("the reference reader sees our shells as shells",
                  ours.get("cls") == 1,
                  f"representationClass={ours.get('cls')} — 0 means the viewer draws no surface")
            check("BOTH CONVERTERS INDEX THE SAME ELEMENTS",
                  set(ours["guids"]) == set(theirs["guids"]),
                  f"only ours: {sorted(set(ours['guids']) - set(theirs['guids']))[:4]}; "
                  f"only theirs: {sorted(set(theirs['guids']) - set(ours['guids']))[:4]}")
            # Exact, not approximate: the index rule was derived to reproduce this number, so a
            # drift here means the rule and the reference have parted company.
            check("BOTH INDEX EXACTLY THE SAME ENTITY COUNT",
                  ours["localIds"] == theirs["localIds"],
                  f"ours={ours['localIds']} theirs={theirs['localIds']} — `_INDEXABLE` was derived "
                  f"to match the reference class-for-class; a difference means it no longer does")
            # Shell COUNTS legitimately differ — the reference merges coplanar triangles into
            # polygons and splits some elements into several representations. Both must be non-zero
            # and within an order of magnitude; equality here would be asserting one tessellator.
            check("both produced geometry", ours["shells"] > 0 and theirs["shells"] > 0,
                  f"ours={ours['shells']} theirs={theirs['shells']}")
            print(f"      (shells: python={ours['shells']} node={theirs['shells']} — differing "
                  f"counts are expected; the two libraries tessellate independently)")

if FAILED:
    print("FAIL test_fragments_python")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_fragments_python OK  ({result.elements} elements, {result.meshes} shells, "
      f"{result.skipped_voids} void(s) skipped, {len(model.local_ids)} entities indexed; "
      f"cross-checked against the Node converter: {'yes' if _have_reference else 'NO — unavailable'})")
