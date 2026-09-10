"""The `.frag` binary layout, derived from the shipped `@thatopen/fragments` reader — ONE place.

**A `.frag` file is `zlib(flatbuffers)`.** No `.fbs` schema ships with the package, so this layout
was recovered from the FlatBuffers accessors generated into
`node_modules/@thatopen/fragments/dist/index.mjs` and then VERIFIED by parsing a reference file the
Node converter produced. Both halves matter: the accessors give the vtable slots and strides, and
the reference file proves the reading is right rather than plausible.

**Why this exists at all.** The desktop app ships no Node runtime, so `services/converter/src/cli.mjs`
— the only IFC->Fragments path — can never run there, and `GET /projects/{pid}/model.frag` is 404
forever in the packaged product (DESKTOP-FRAGMENTS). This is the Python side of that path:
`ifcopenshell` already does the tessellation and is already bundled.

**The risk this carries, named rather than buried.** A second implementation of a format is a second
thing that can disagree with the first. The mitigation is not care, it is measurement: the
conformance gate converts one IFC through BOTH paths and asserts the results agree on the facts that
matter (element GUIDs, mesh counts, bounding boxes within tolerance) — and, decisively, loads the
Python output with the REAL `@thatopen/fragments` library. Geometry is *expected* to differ in
triangulation, because web-ifc and IfcOpenShell tessellate independently; what must not differ is
which elements exist, where they are, and whether the reference reader accepts the file.

**Version coupling.** These offsets belong to `@thatopen/fragments` 3.4.7, pinned in
`apps/web/package.json`. A major bump can change the schema, which is exactly the coupling hazard
CLAUDE.md names for this package pair. `services/api/test_fragments_schema.py` re-derives the slots
from the INSTALLED package and fails when they move, so the pin and this file cannot drift apart
silently.
"""
from __future__ import annotations

#: The `@thatopen/fragments` release these offsets were read from. Asserted against the installed
#: package by the schema gate — a bump that changes the layout must update both.
FRAGMENTS_VERSION = "3.4.7"

# --- table field slots (FlatBuffers vtable offsets) ------------------------------------------------
# A slot is `4 + 2*field_index`. Read straight off the generated `__offset(this.bb_pos, N)` calls.

#: `Model` — the root table.
MODEL = {
    "metadata": 4,            # string, a JSON blob (schema, names, ...)
    "guids": 6,               # [string]  IFC GlobalIds
    "guids_items": 8,         # [uint32]  local id per guid
    "max_local_id": 10,       # uint32
    "local_ids": 12,          # [uint32]
    "categories": 14,         # [string]  IFC class per local id, e.g. "IFCWALL"
    "meshes": 16,             # Meshes (table)
    "attributes": 18,         # [Attribute]
    "relations": 20,          # [Relation]
    "relations_items": 22,    # [int32]
    "guid": 24,               # string, the model's own id
    "spatial_structure": 26,  # SpatialStructure (table)
    "unique_attributes": 28,  # [string]
    "relation_names": 30,     # [string]
    "indexes": 32,            # [ModelIndex]
}
#: How many fields `Model` declares — `builder.startObject(15)` in the generated writer.
MODEL_FIELDS = 15

#: `Meshes` — the geometry payload.
MESHES = {
    # `coordinates` is an inline `Transform` STRUCT, not a table — `addFieldStruct(0, ...)` in the
    # generated writer. Recorded wrong here at first ("DoubleVector (table)"), which is why `dumps`
    # omitted it and `loads` tried to follow a table offset. The reference viewer's `getCoordinates`
    # dereferences it with no null check, so a fragment without it does not degrade — it throws.
    "coordinates": 4,         # Transform (inline struct): the model's real-world placement
    "meshes_items": 6,        # [uint32]  local id per mesh item
    "samples": 8,             # [Sample]  struct, stride 16
    "representations": 10,    # [Representation] struct, stride 32
    "materials": 12,          # [Material] struct, stride 6
    "circle_extrusions": 14,  # [CircleExtrusion] table
    "shells": 16,             # [Shell] table
    "local_transforms": 18,   # [Transform] struct, stride 48
    "global_transforms": 20,  # [Transform] struct, stride 48
    "material_ids": 22,       # [uint32]
    "representation_ids": 24, # [uint32]
    "sample_ids": 26,         # [uint32]
}
MESHES_FIELDS = 12

#: `Shell` — a polygonal boundary representation. **Not a triangle soup**: `points` are the
#: vertices and `profiles` are index loops around each planar face, which is why the browser
#: pulls in `earcut`. A triangle is simply a three-index profile, which is what this writer emits.
SHELL = {
    "profiles": 4,            # [ShellProfile] table — outer loops
    "holes": 6,               # [ShellHole] table — inner loops
    "points": 8,              # [FloatVector] struct, stride 12
    "big_profiles": 10,       # [BigShellProfile] — for shells past the uint16 index ceiling
    "big_holes": 12,          # [BigShellHole]
    "type": 14,               # uint8
}
SHELL_FIELDS = 6

#: `ShellProfile.indices` is **uint16**, so one shell addresses at most 65,536 points. Past that the
#: `big_*` variants carry uint32 indices. The writer splits a mesh into several shells rather than
#: silently truncating — a wrapped index draws a face between unrelated corners, which looks like a
#: modelling error rather than a converter bug.
SHELL_PROFILE = {"indices": 4}
SHELL_PROFILE_FIELDS = 1
#: The exclusive ceiling on points addressable by a uint16 profile index.
MAX_SHELL_POINTS = 1 << 16

# --- struct strides and field offsets --------------------------------------------------------------
# Structs are inline and fixed-size: no vtable, so these are byte offsets from the struct start.

#: `Sample` (16 B): which item, material, representation and transform one drawn instance uses.
SAMPLE_STRIDE = 16
SAMPLE = {"item": 0, "material": 4, "representation": 8, "local_transform": 12}   # all uint32

#: `Representation` (32 B): id, bounding box, and a class tag (1 == shell).
REPRESENTATION_STRIDE = 32
REPRESENTATION = {"id": 0, "bbox_min": 4, "bbox_max": 16, "representation_class": 28}
#: `representation_class` value for a shell — read off the reference file, not guessed.
REPRESENTATION_CLASS_SHELL = 1

#: `Material` (6 B): RGBA bytes plus two flags.
MATERIAL_STRIDE = 6
MATERIAL = {"r": 0, "g": 1, "b": 2, "a": 3, "rendered_faces": 4, "stroke": 5}

#: `Transform` (48 B): a double-precision position and two single-precision direction vectors.
#: The third axis is implied by the cross product, which is why only two are stored.
TRANSFORM_STRIDE = 48
TRANSFORM = {"position": 0, "x_direction": 24, "y_direction": 36}

#: `FloatVector` (12 B) / `DoubleVector` (24 B) — three components each.
FLOAT_VECTOR_STRIDE = 12
DOUBLE_VECTOR_STRIDE = 24
#: `BoundingBox` (24 B) — two FloatVectors, min then max.
BOUNDING_BOX_STRIDE = 24
