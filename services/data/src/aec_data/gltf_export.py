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
import multiprocessing
from typing import Any

import ifcopenshell
import ifcopenshell.geom as geom
import numpy as np

# Z-up (IFC) -> Y-up (glTF): rotate -90° about X, i.e. (x, y, z) -> (x, z, -y).
_ZUP_TO_YUP = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64)


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
    it = geom.iterator(settings, model, max(1, multiprocessing.cpu_count() - 1))
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


def export_gltf(model: ifcopenshell.file, name: str = "model") -> dict[str, Any]:
    """Build a self-contained glTF 2.0 document (dict) for the whole model, one node per IFC class."""
    merged = _baked_by_class(model)
    blob = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    materials: list[dict] = []
    meshes: list[dict] = []
    nodes: list[int] = []
    node_list: list[dict] = []

    for cls, (verts, faces) in sorted(merged.items()):
        idx = faces.reshape(-1).astype(np.uint32)
        vflat = verts.astype(np.float32)
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
        accessors.append({"bufferView": len(buffer_views) - 1, "componentType": 5125,
                          "count": int(len(idx)), "type": "SCALAR"})
        # material + mesh + node
        materials.append({"name": cls, "pbrMetallicRoughness":
                          {"baseColorFactor": _class_colour(cls), "metallicFactor": 0.0,
                           "roughnessFactor": 0.9}, "doubleSided": True})
        meshes.append({"name": cls, "primitives": [{"attributes": {"POSITION": pos_acc},
                       "indices": idx_acc, "material": len(materials) - 1, "mode": 4}]})
        node_list.append({"name": cls, "mesh": len(meshes) - 1})
        nodes.append(len(node_list) - 1)

    uri = "data:application/octet-stream;base64," + base64.b64encode(bytes(blob)).decode("ascii")
    return {
        "asset": {"version": "2.0", "generator": "Massing glTF export (ifcopenshell)"},
        "scene": 0,
        "scenes": [{"name": name, "nodes": nodes}],
        "nodes": node_list,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(blob), "uri": uri}],
    }


def export_gltf_bytes(ifc_path: str, name: str = "model") -> bytes:
    """Open an IFC file and return a self-contained ``.gltf`` (UTF-8 JSON) of its geometry."""
    from .ifc_loader import open_model
    doc = export_gltf(open_model(ifc_path), name)
    return json.dumps(doc, separators=(",", ":")).encode("utf-8")
