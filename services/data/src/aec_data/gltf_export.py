"""Server-side glTF 2.0 export of the model geometry (the tractable slice of geometry export).

The viewer streams Fragments (.frag); this is the *interchange* path — a self-contained, standard
glTF 2.0 file that any DCC / web viewer / Blender / Three.js reads. We triangulate every element with
the same ``ifcopenshell.geom`` iterator the section/clash tools already use, flip Z-up → Y-up (glTF
convention), and merge elements **per IFC class** so each class is one mesh/node with a stable colour —
viewable and organised without an explosion of nodes.

Honest scope: triangulated meshes + per-class flat colours. No PBR materials, textures, or per-element
nodes — those need the authoring geometry graph, not the tessellation. A single self-contained ``.gltf``
(binary buffer embedded as a base64 data-URI) so there's no sidecar ``.bin`` to keep together.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import ifcopenshell
import ifcopenshell.geom as geom
import numpy as np

from .geomconf import bounded_iterator

# Z-up (IFC) -> Y-up (glTF): rotate -90° about X, i.e. (x, y, z) -> (x, z, -y).
_ZUP_TO_YUP = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64)

#: Draco's default. 14 bits spreads the mesh's bounding box over 16,384 steps per axis, so the
#: worst-case position error is `bbox_extent / 16384` — about 6 mm on a 100 m building, 1 mm on a 16 m
#: one. Stated rather than assumed because it is the whole cost of the option: see `draco_accuracy()`.
DEFAULT_QUANTIZATION_BITS = 14

#: Raised when the caller asks for Draco and the optional dependency is not installed. The message is
#: the actionable half — a bare ImportError names a module the caller has no reason to have heard of.
DRACO_UNAVAILABLE = (
    "Draco compression was requested but the optional 'DracoPy' package is not installed. "
    "Install it (pip install DracoPy==1.7.0) or export without draco=True — the uncompressed "
    "export is standard glTF 2.0 and needs no extension support."
)


class DracoUnavailable(RuntimeError):
    """The caller asked for Draco and DracoPy is not importable."""


def draco_available() -> bool:
    """Whether Draco compression can be used in this process.

    Deliberately a probe rather than a module-level import: Draco is OPTIONAL. The uncompressed path
    is the contract this module advertises — "any DCC / web viewer / Blender / Three.js reads it" —
    and a hard import would make an optional extension a hard requirement for the export that does not
    use it.
    """
    try:
        import DracoPy  # noqa: F401
        return True
    except Exception:
        return False


def draco_accuracy(bbox_extent: float, quantization_bits: int = DEFAULT_QUANTIZATION_BITS) -> float:
    """Worst-case position error, in model units, that Draco quantization introduces.

    Draco spreads each axis of the mesh's bounding box over ``2**bits`` steps, so the error is a
    function of MODEL SIZE, not of the geometry's detail: the same setting that is imperceptible on a
    16 m house is ~6 mm on a 100 m tower and ~60 mm on a 1 km site. Callers deciding whether the
    option is acceptable need that number, and it cannot be quoted as a single figure.
    """
    return bbox_extent / float(2 ** quantization_bits)


def _class_colour(cls: str) -> list[float]:
    """A stable, readable RGBA per IFC class (deterministic hash → hue), so exports colour the same."""
    h = (hash(cls) % 360) / 360.0
    # simple HSV(h, 0.45, 0.85) → RGB
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, 0.45, 0.85)
    return [round(r, 4), round(g, 4), round(b, 4), 1.0]


def _baked_by_class(model: ifcopenshell.file) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Triangulate every element; merge vertices+faces per IFC class into (verts Nx3, faces Mx3)."""
    settings = geom.settings()
    it = bounded_iterator(geom, settings, model)
    acc: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
    if not it.initialize():
        return {}
    while True:
        shape = it.get()
        verts = np.asarray(shape.geometry.verts, dtype=np.float64).reshape(-1, 3)
        faces = np.asarray(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
        if verts.size and faces.size:
            el = model.by_guid(shape.guid)
            cls = el.is_a() if el else (shape.type or "IfcProduct")
            acc.setdefault(cls, []).append((verts @ _ZUP_TO_YUP.T, faces))
        if not it.next():
            break
    merged: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for cls, parts in acc.items():
        offset = 0
        vlist, flist = [], []
        for verts, faces in parts:
            vlist.append(verts)
            flist.append(faces + offset)
            offset += len(verts)
        merged[cls] = (np.vstack(vlist), np.vstack(flist))
    return merged


def _pad4(buf: bytearray) -> None:
    while len(buf) % 4:
        buf.append(0)


def _draco_primitive(vflat: np.ndarray, faces: np.ndarray, blob: bytearray,
                     buffer_views: list[dict], accessors: list[dict],
                     quantization_bits: int) -> tuple[int, int, int, int]:
    """Encode one mesh with Draco and emit its bufferView + the two accessors the extension needs.

    Returns ``(pos_accessor, idx_accessor, draco_bufferView, draco_position_attribute_id)``.

    **The counts come from decoding what we just encoded, never from the input.** Draco dedups and
    REORDERS vertices — a 5-vertex input measured here came back as 4, in a different order — so the
    POSITION accessor's `count` and `min`/`max` describe the decoded mesh or they describe nothing.
    Writing the input's count produces a file that validates structurally and disagrees with its own
    payload, which is the failure shape worth the extra decode.
    """
    import DracoPy

    encoded = DracoPy.encode(vflat, faces.astype(np.uint32), quantization_bits=quantization_bits)
    decoded = DracoPy.decode(encoded)
    dpts = np.asarray(decoded.points, dtype=np.float32).reshape(-1, 3)
    dfaces = np.asarray(decoded.faces).reshape(-1, 3)

    # The glTF attribute -> Draco attribute-id map. Read off the encoder's own output rather than
    # hard-coded to 0: the id is the encoder's to assign, and a wrong one is a file no loader reads.
    pos_id = next((a["unique_id"] for a in decoded.attributes if a.get("attribute_type") == 0), 0)

    offset = len(blob)
    blob.extend(encoded)
    _pad4(blob)
    buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(encoded)})
    dv = len(buffer_views) - 1

    # Both accessors OMIT bufferView — per KHR_draco_mesh_compression the data lives in the Draco
    # buffer, and the accessor exists to declare type/count/bounds to a loader that has not yet
    # decoded it.
    pos_acc = len(accessors)
    accessors.append({"componentType": 5126, "count": int(len(dpts)), "type": "VEC3",
                      "min": dpts.min(axis=0).tolist(), "max": dpts.max(axis=0).tolist()})
    idx_acc = len(accessors)
    accessors.append({"componentType": 5125, "count": int(dfaces.size), "type": "SCALAR"})
    return pos_acc, idx_acc, dv, int(pos_id)


def _decimate_merged(merged: dict, max_faces_per_class: int) -> dict:
    """Apply a per-class triangle budget by vertex clustering.

    Per CLASS, not per model, because that is the unit the export already merges into — and a global
    budget would spend it all on whichever class happens to sort first. `decimate_to_budget` returns
    the input untouched when it already fits, so a small class is never degraded to satisfy a ceiling
    it was already under.
    """
    from massingviser_geometry import decimate_to_budget  # type: ignore

    out = {}
    for cls, (verts, faces) in merged.items():
        if len(faces) <= max_faces_per_class:
            out[cls] = (verts, faces)
            continue
        d = decimate_to_budget(verts, faces, max_faces=max_faces_per_class)
        # An empty result would silently delete a whole discipline from the export. Keep the original
        # rather than ship a hole: losing detail is the trade being made, losing the element is not.
        out[cls] = (d.vertices, d.faces) if d.face_count > 0 else (verts, faces)
    return out


def _build_gltf_doc(model: ifcopenshell.file, name: str, *, draco: bool = False,
                    quantization_bits: int = DEFAULT_QUANTIZATION_BITS,
                    max_faces_per_class: int | None = None) -> tuple[dict[str, Any], bytes]:
    """Build the glTF 2.0 document (one node per IFC class) plus the raw binary buffer, WITHOUT a buffer
    URI. The `.gltf` path adds an embedded data URI; the `.glb` path packs the buffer as a binary chunk.

    ``draco=True`` compresses each mesh with KHR_draco_mesh_compression. It is OFF by default and that
    is deliberate: the extension is *required*, not optional, for any file that uses it, so a consumer
    without a Draco decoder reads nothing at all. The default export stays universally readable.

    ``max_faces_per_class`` caps triangles per IFC class by **vertex-clustering decimation**, so a
    consumer receives a budget rather than a model. Off by default — decimation is lossy, and a
    coordination or takeoff consumer wants the real geometry. It is for viewers and engines that need
    a whole building to arrive, not a faithful one.

    NOTE this is geometric level of DETAIL, and is unrelated to `aec_api/lod.py`, which is level of
    DEVELOPMENT (LOD 100-500, BIM maturity). The names collide; the concepts do not touch.
    """
    if draco and not draco_available():
        raise DracoUnavailable(DRACO_UNAVAILABLE)
    merged = _baked_by_class(model)
    if max_faces_per_class:
        merged = _decimate_merged(merged, max_faces_per_class)
    blob = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    materials: list[dict] = []
    meshes: list[dict] = []
    nodes: list[int] = []
    node_list: list[dict] = []

    for cls, (verts, faces) in sorted(merged.items()):
        vflat = verts.astype(np.float32)
        if draco:
            pos_acc, idx_acc, dv, pos_id = _draco_primitive(
                vflat, faces, blob, buffer_views, accessors, quantization_bits)
            materials.append({"name": cls, "pbrMetallicRoughness":
                              {"baseColorFactor": _class_colour(cls), "metallicFactor": 0.0,
                               "roughnessFactor": 0.9}, "doubleSided": True})
            meshes.append({"name": cls, "primitives": [{
                "attributes": {"POSITION": pos_acc}, "indices": idx_acc,
                "material": len(materials) - 1, "mode": 4,
                "extensions": {"KHR_draco_mesh_compression": {
                    "bufferView": dv, "attributes": {"POSITION": pos_id}}}}]})
            node_list.append({"name": cls, "mesh": len(meshes) - 1})
            nodes.append(len(node_list) - 1)
            continue
        # INDEX WIDTH is chosen per mesh, not fixed at uint32. Indices were 60% of the geometry in a
        # measured 175 KB export and every mesh was far under the uint16 ceiling, so a fixed uint32
        # was paying double for the majority of the file. uint16 indices are core glTF 2.0 — no
        # extension, no loader support to check — so this costs nothing in compatibility.
        # The ceiling is on the VERTEX COUNT, not the index count: an index must address vertex
        # `len(vflat) - 1`, so the test is on vertices. Getting that wrong silently truncates
        # geometry on any mesh past 65,535 verts, which is why it is written as the vertex bound.
        if len(vflat) <= 65536:
            idx = faces.reshape(-1).astype(np.uint16)
            idx_component = 5123
        else:
            idx = faces.reshape(-1).astype(np.uint32)
            idx_component = 5125
        # positions bufferView + accessor
        pos_offset = len(blob)
        blob.extend(vflat.tobytes())
        _pad4(blob)
        buffer_views.append({"buffer": 0, "byteOffset": pos_offset,
                             "byteLength": vflat.nbytes, "target": 34962})
        pos_acc = len(accessors)
        accessors.append({"bufferView": len(buffer_views) - 1, "componentType": 5126,
                          "count": int(len(vflat)), "type": "VEC3",
                          "min": vflat.min(axis=0).tolist(), "max": vflat.max(axis=0).tolist()})
        # indices bufferView + accessor
        idx_offset = len(blob)
        blob.extend(idx.tobytes())
        _pad4(blob)
        buffer_views.append({"buffer": 0, "byteOffset": idx_offset,
                             "byteLength": idx.nbytes, "target": 34963})
        idx_acc = len(accessors)
        accessors.append({"bufferView": len(buffer_views) - 1, "componentType": idx_component,
                          "count": int(len(idx)), "type": "SCALAR"})
        # material + mesh + node
        materials.append({"name": cls, "pbrMetallicRoughness":
                          {"baseColorFactor": _class_colour(cls), "metallicFactor": 0.0,
                           "roughnessFactor": 0.9}, "doubleSided": True})
        meshes.append({"name": cls, "primitives": [{"attributes": {"POSITION": pos_acc},
                       "indices": idx_acc, "material": len(materials) - 1, "mode": 4}]})
        node_list.append({"name": cls, "mesh": len(meshes) - 1})
        nodes.append(len(node_list) - 1)

    doc = {
        "asset": {"version": "2.0", "generator": "Massing glTF export (ifcopenshell)"},
        "scene": 0,
        "scenes": [{"name": name, "nodes": nodes}],
        "nodes": node_list,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(blob)}],       # no uri yet — the .gltf/.glb path fills it in
    }
    if draco:
        # REQUIRED, not merely used. A Draco primitive carries no fallback geometry, so a loader
        # without the decoder cannot render a degraded version — it must refuse the file. Declaring it
        # only in `extensionsUsed` would tell that loader the file is safe to open, and it would then
        # silently draw nothing. This is the honest declaration and it is why draco is opt-in.
        doc["extensionsUsed"] = ["KHR_draco_mesh_compression"]
        doc["extensionsRequired"] = ["KHR_draco_mesh_compression"]
    return doc, bytes(blob)


def export_gltf(model: ifcopenshell.file, name: str = "model", *, draco: bool = False,
                quantization_bits: int = DEFAULT_QUANTIZATION_BITS,
                max_faces_per_class: int | None = None) -> dict[str, Any]:
    """A self-contained glTF 2.0 document (dict) for the whole model — the binary buffer embedded as a
    base64 data URI, so the JSON is standalone.

    ``max_faces_per_class`` decimates to a per-class triangle budget (see `_build_gltf_doc`)."""
    doc, blob = _build_gltf_doc(model, name, draco=draco, quantization_bits=quantization_bits,
                                max_faces_per_class=max_faces_per_class)
    doc["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(blob).decode("ascii")
    return doc


def export_gltf_bytes(ifc_path: str, name: str = "model", *, draco: bool = False,
                      quantization_bits: int = DEFAULT_QUANTIZATION_BITS,
                      max_faces_per_class: int | None = None) -> bytes:
    """Open an IFC file and return a self-contained ``.gltf`` (UTF-8 JSON) of its geometry."""
    from .ifc_loader import open_model
    doc = export_gltf(open_model(ifc_path), name, draco=draco, quantization_bits=quantization_bits)
    return json.dumps(doc, separators=(",", ":")).encode("utf-8")


def _pack_glb(doc: dict[str, Any], blob: bytes) -> bytes:
    """Pack a glTF document + its binary buffer into a single binary ``.glb`` container (glTF 2.0): a
    12-byte header, a JSON chunk (space-padded to 4), and a BIN chunk (zero-padded to 4). The buffer must
    carry NO uri (the BIN chunk is the buffer)."""
    import struct

    json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    bin_blob = blob + b"\x00" * ((4 - len(blob) % 4) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)          # magic 'glTF', version 2, total length
    out += struct.pack("<II", len(json_bytes), 0x4E4F534A)    # JSON chunk header (length, 'JSON')
    out += json_bytes
    out += struct.pack("<II", len(bin_blob), 0x004E4942)      # BIN chunk header (length, 'BIN\0')
    out += bin_blob
    return bytes(out)


def export_glb_bytes(ifc_path: str, name: str = "model", *, draco: bool = False,
                     quantization_bits: int = DEFAULT_QUANTIZATION_BITS) -> bytes:
    """Open an IFC file and return a binary ``.glb`` (glTF 2.0 container) of its geometry — the compact,
    single-file form most 3D tools (Blender, three.js, game engines) import directly."""
    from .ifc_loader import open_model
    doc, blob = _build_gltf_doc(open_model(ifc_path), name, draco=draco,
                                quantization_bits=quantization_bits)
    return _pack_glb(doc, blob)
