"""BCF .bcfzip import/export (guide §7).

A pragmatic subset of buildingSMART BCF: one folder per topic GUID containing markup.bcf
(topic + comments) and, when present, viewpoint.bcfv (camera + components). This round-trips
the spine that Solibri / ACC / BIMcollab read.

Both **BCF 2.1** and **BCF 3.0** are supported. The two differ mainly in markup.bcf shape:
in 3.0 the `<Comment>`s and `<Viewpoints>` move *inside* `<Topic>`, and `<Labels>` become a
`<Labels><Label>…</Label></Labels>` group (2.1 uses bare repeated `<Labels>` and puts comments /
viewpoints as siblings of `<Topic>`). The visualization info (.bcfv) is effectively unchanged.
Export defaults to 2.1 (universally accepted); pass `version="3.0"` to emit 3.0. **Import
auto-detects** the version from `bcf.version` and reads both shapes, so a 3.0 file from a newer
BIMcollab / ACC no longer silently drops its comments and labels."""
from __future__ import annotations

import io
import os
import xml.etree.ElementTree as ET  # for Element node types only — parsing goes through defusedxml
import zipfile
from datetime import datetime, timezone
from typing import Any

# BCF files are user-uploaded, untrusted XML inside a zip. Parse with defusedxml to harden against
# XXE / billion-laughs / external-entity attacks (same protection as citygml.py). Returns standard
# ElementTree nodes, so the rest of the ET-based traversal is unchanged.
from defusedxml.ElementTree import fromstring as _safe_fromstring
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Comment, Topic, Viewpoint

# Decompression-bomb guard: the raw upload is capped by AEC_MAX_UPLOAD_MB, but a tiny zip can still
# expand to gigabytes in RAM. Cap each entry AND the running total of uncompressed bytes.
_MAX_UNZIP_MB = int(os.environ.get("AEC_MAX_UNZIP_MB", "512"))
_MAX_UNZIP_BYTES = _MAX_UNZIP_MB * 1024 * 1024


def _open_bcfzip(data: bytes) -> zipfile.ZipFile:
    """Open a .bcfzip, rejecting decompression bombs by checking the declared uncompressed size of
    each entry and the cumulative total against AEC_MAX_UNZIP_MB (default 512)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(422, "not a valid .bcfzip (bad zip archive)")
    total = 0
    for info in z.infolist():
        total += info.file_size
        if info.file_size > _MAX_UNZIP_BYTES or total > _MAX_UNZIP_BYTES:
            z.close()
            raise HTTPException(413, f"BCF zip exceeds the {_MAX_UNZIP_MB} MB uncompressed limit "
                                     "(possible decompression bomb)")
    return z

_BCF_VERSION = "2.1"          # default export version
_BCF_VERSIONS = ("2.1", "3.0")
SUPPORTED_VERSIONS = _BCF_VERSIONS   # public: the versions this engine reads + writes (openbim registry)


def _norm_version(v: str | None) -> str:
    """Coerce to a supported version string; anything starting '3' -> 3.0, else 2.1."""
    s = str(v or "").strip()
    return "3.0" if s.startswith("3") else "2.1"


def _iso(dt: datetime | None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _labels_xml(parent: ET.Element, labels, version: str) -> None:
    """2.1: bare repeated <Labels>. 3.0: a <Labels> group of <Label> children."""
    if not labels:
        return
    if version == "3.0":
        grp = ET.SubElement(parent, "Labels")
        for label in labels:
            ET.SubElement(grp, "Label").text = label
    else:
        for label in labels:
            ET.SubElement(parent, "Labels").text = label


def _comment_xml(parent: ET.Element, c) -> None:
    ce = ET.SubElement(parent, "Comment", {"Guid": c.id})
    ET.SubElement(ce, "Date").text = _iso(c.created_at)
    if c.author:
        ET.SubElement(ce, "Author").text = c.author
    ET.SubElement(ce, "Comment").text = c.text
    if c.viewpoint_id:
        ET.SubElement(ce, "Viewpoint", {"Guid": c.viewpoint_id})


def _markup_xml(topic: Topic, version: str = _BCF_VERSION) -> bytes:
    version = _norm_version(version)
    is3 = version == "3.0"
    root = ET.Element("Markup")
    t = ET.SubElement(root, "Topic", {"Guid": topic.guid, "TopicType": topic.type, "TopicStatus": topic.status})
    ET.SubElement(t, "Title").text = topic.title or ""
    if topic.priority:
        ET.SubElement(t, "Priority").text = topic.priority
    _labels_xml(t, topic.labels, version)
    ET.SubElement(t, "CreationDate").text = _iso(topic.created_at)
    if topic.author:
        ET.SubElement(t, "CreationAuthor").text = topic.author
    if topic.assignee:
        ET.SubElement(t, "AssignedTo").text = topic.assignee
    if topic.description:
        ET.SubElement(t, "Description").text = topic.description

    # 3.0 nests comments + viewpoints INSIDE <Topic>; 2.1 has them as siblings of <Topic>.
    comment_parent = ET.SubElement(t, "Comments") if (is3 and topic.comments) else root
    for c in topic.comments:
        _comment_xml(comment_parent, c)

    vp_parent = ET.SubElement(t, "Viewpoints") if is3 else None
    def add_vp(guid: str) -> None:
        if is3:
            vp = ET.SubElement(vp_parent, "ViewPoint", {"Guid": guid})
            ET.SubElement(vp, "Viewpoint").text = f"{guid}.bcfv"
        else:
            vp = ET.SubElement(root, "Viewpoints", {"Guid": guid})
            ET.SubElement(vp, "Viewpoint").text = f"{guid}.bcfv"

    has_vp = False
    for v in topic.viewpoints:
        add_vp(v.guid)
        has_vp = True
    # a pin (anchor + element GUIDs) with no explicit viewpoint still needs a .bcfv so the element
    # tie + camera survive the round-trip (the GlobalId tie is a non-negotiable)
    if not has_vp and (topic.anchor or topic.element_guids):
        add_vp(topic.guid)
    if is3 and vp_parent is not None and len(vp_parent) == 0:
        t.remove(vp_parent)   # don't emit an empty <Viewpoints> container
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _xyz(parent: ET.Element, d: dict) -> None:
    ET.SubElement(parent, "X").text = str(d.get("x", 0))
    ET.SubElement(parent, "Y").text = str(d.get("y", 0))
    ET.SubElement(parent, "Z").text = str(d.get("z", 0))


def _direction(cam: dict) -> dict:
    """Camera direction: explicit `direction`, else derived from position -> target (normalized)."""
    if cam.get("direction"):
        return cam["direction"]
    p, t = cam.get("position") or {}, cam.get("target")
    if not t:
        return {"x": 0, "y": 0, "z": -1}
    dx, dy, dz = t.get("x", 0) - p.get("x", 0), t.get("y", 0) - p.get("y", 0), t.get("z", 0) - p.get("z", 0)
    n = (dx * dx + dy * dy + dz * dz) ** 0.5 or 1.0
    return {"x": dx / n, "y": dy / n, "z": dz / n}


def _camera_xml(root: ET.Element, cam: dict) -> None:
    """Emit a full BCF 2.1 camera — PerspectiveCamera or OrthogonalCamera per `cam['type']` — with
    view point, direction, up vector, and field-of-view / view-to-world-scale (prior versions dropped
    everything but the view point, so restoring a viewpoint lost the actual view and all ortho/section
    cameras)."""
    is_ortho = str(cam.get("type", "perspective")).lower().startswith("ortho")
    el = ET.SubElement(root, "OrthogonalCamera" if is_ortho else "PerspectiveCamera")
    ET.SubElement(el, "CameraViewPoint"); _xyz(el.find("CameraViewPoint"), cam.get("position", {}))
    ET.SubElement(el, "CameraDirection"); _xyz(el.find("CameraDirection"), _direction(cam))
    ET.SubElement(el, "CameraUpVector"); _xyz(el.find("CameraUpVector"), cam.get("up", {"x": 0, "y": 0, "z": 1}))
    if is_ortho:
        ET.SubElement(el, "ViewToWorldScale").text = str(cam.get("view_to_world_scale", cam.get("scale", 1.0)))
    else:
        ET.SubElement(el, "FieldOfView").text = str(cam.get("fov", 60))


def _coloring_xml(comps_el: ET.Element, coloring: list) -> None:
    """Emit per-element Coloring: [{color:'FF0000', guids:[...]}] -> <Coloring><Color><Component/>…"""
    col = ET.SubElement(comps_el, "Coloring")
    for c in coloring:
        ce = ET.SubElement(col, "Color", {"Color": str(c.get("color", "FFFFFF"))})
        for g in c.get("guids", []):
            ET.SubElement(ce, "Component", {"IfcGuid": g})


def _viewpoint_xml(v: Viewpoint) -> bytes:
    root = ET.Element("VisualizationInfo", {"Guid": v.guid})
    coloring = (v.visibility or {}).get("coloring") if v.visibility else None
    if v.components or v.visibility or coloring:
        comps = ET.SubElement(root, "Components")
        if v.components:
            sel = ET.SubElement(comps, "Selection")
            for guid in v.components:
                ET.SubElement(sel, "Component", {"IfcGuid": guid})
        if coloring:
            _coloring_xml(comps, coloring)
        if v.visibility:
            vis = ET.SubElement(comps, "Visibility",
                                {"DefaultVisibility": str(v.visibility.get("default_visibility", True)).lower()})
            exc = ET.SubElement(vis, "Exceptions")
            for guid in v.visibility.get("exceptions", []):
                ET.SubElement(exc, "Component", {"IfcGuid": guid})
    if v.camera:
        _camera_xml(root, v.camera)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _parse_camera(vroot: ET.Element) -> dict | None:
    """Read a PerspectiveCamera or OrthogonalCamera into {type, position, direction, up, fov|scale}."""
    for tag, kind in (("PerspectiveCamera", "perspective"), ("OrthogonalCamera", "orthographic")):
        cel = vroot.find(tag)
        if cel is None:
            continue
        def pt(name: str, cel: ET.Element = cel) -> dict | None:   # bind loop var (B023)
            e = cel.find(name)
            return {ax.lower(): float(e.findtext(ax) or 0) for ax in ("X", "Y", "Z")} if e is not None else None
        cam: dict[str, Any] = {"type": kind, "position": pt("CameraViewPoint") or {"x": 0, "y": 0, "z": 0}}
        if pt("CameraDirection"):
            cam["direction"] = pt("CameraDirection")
        if pt("CameraUpVector"):
            cam["up"] = pt("CameraUpVector")
        if kind == "orthographic":
            cam["view_to_world_scale"] = float(cel.findtext("ViewToWorldScale") or 1.0)
        else:
            cam["fov"] = float(cel.findtext("FieldOfView") or 60)
        return cam
    return None


def _parse_coloring(vroot: ET.Element) -> list:
    out = []
    for color in vroot.findall(".//Coloring/Color"):
        guids = [c.get("IfcGuid") for c in color.findall("Component") if c.get("IfcGuid")]
        if guids:
            out.append({"color": color.get("Color", "FFFFFF"), "guids": guids})
    return out


def _all_comments(root: ET.Element, te: ET.Element | None):
    """Comment elements, whether 2.1 (siblings of <Topic>) or 3.0 (nested <Topic><Comments><Comment>)."""
    out = list(root.findall("Comment"))
    if te is not None:
        out += te.findall("Comments/Comment")
    return out


def _all_labels(te: ET.Element) -> list[str]:
    """Labels, whether 2.1 (bare repeated <Labels>text) or 3.0 (grouped <Labels><Label>text)."""
    out = [e.text.strip() for e in te.findall("Labels") if e.text and e.text.strip()]     # 2.1 bare
    out += [e.text.strip() for e in te.findall("Labels/Label") if e.text and e.text.strip()]  # 3.0 group
    return out


def export_bcfzip(db: Session, project_id: str, version: str = _BCF_VERSION) -> bytes:
    version = _norm_version(version)
    topics = db.query(Topic).filter(Topic.project_id == project_id).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        bsmart = ET.Element("Version", {"VersionId": version})
        z.writestr("bcf.version", ET.tostring(bsmart, encoding="utf-8", xml_declaration=True))
        for topic in topics:
            z.writestr(f"{topic.guid}/markup.bcf", _markup_xml(topic, version))
            wrote_vp = False
            for v in topic.viewpoints:
                z.writestr(f"{topic.guid}/{v.guid}.bcfv", _viewpoint_xml(v))
                wrote_vp = True
            if not wrote_vp and (topic.anchor or topic.element_guids):
                z.writestr(f"{topic.guid}/{topic.guid}.bcfv",
                           _record_viewpoint_xml(topic.guid, topic.element_guids or [], topic.anchor))
    return buf.getvalue()


def _record_viewpoint_xml(guid: str, components: list[str], anchor: dict | None) -> bytes:
    root = ET.Element("VisualizationInfo", {"Guid": guid})
    if components:
        comps = ET.SubElement(root, "Components")
        sel = ET.SubElement(comps, "Selection")
        for g in components:
            ET.SubElement(sel, "Component", {"IfcGuid": g})
    if anchor:
        _camera_xml(root, {"type": "perspective", "position": anchor})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def export_records_bcfzip(records: list[dict], topic_type: str = "Issue",
                          version: str = _BCF_VERSION) -> bytes:
    """Export config-module records (e.g. coordination_issue) as a BCF .bcfzip so they round-trip with
    Solibri / ACC / BIMcollab. Each record → a topic (title/description/priority/status + ref as a
    label); a pinned/element-tied record also gets a viewpoint (selected components + camera at the
    pin). `version` selects BCF 2.1 (default) or 3.0 (comments/viewpoints nest under Topic, grouped
    labels)."""
    version = _norm_version(version)
    is3 = version == "3.0"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bcf.version", ET.tostring(ET.Element("Version", {"VersionId": version}),
                                              encoding="utf-8", xml_declaration=True))
        for r in records:
            guid = str(r.get("id"))
            data = r.get("data") or {}
            root = ET.Element("Markup")
            t = ET.SubElement(root, "Topic", {"Guid": guid, "TopicType": topic_type,
                                              "TopicStatus": r.get("workflow_state") or "open"})
            ET.SubElement(t, "Title").text = r.get("title") or data.get("subject") or r.get("ref") or "Issue"
            if data.get("priority"):
                ET.SubElement(t, "Priority").text = str(data["priority"])
            _labels_xml(t, [r["ref"]] if r.get("ref") else None, version)  # carry our ref so re-import can match
            ET.SubElement(t, "CreationDate").text = _iso(None)
            if r.get("assignee"):
                ET.SubElement(t, "AssignedTo").text = str(r["assignee"])
            if data.get("description"):
                ET.SubElement(t, "Description").text = str(data["description"])
            comps = r.get("element_guids") or []
            anchor = r.get("anchor")
            if comps or anchor:
                vp_parent = ET.SubElement(t, "Viewpoints") if is3 else ET.SubElement(root, "Viewpoints", {"Guid": guid})
                vp = ET.SubElement(vp_parent, "ViewPoint", {"Guid": guid}) if is3 else vp_parent
                ET.SubElement(vp, "Viewpoint").text = f"{guid}.bcfv"
                z.writestr(f"{guid}/{guid}.bcfv", _record_viewpoint_xml(guid, comps, anchor))
            z.writestr(f"{guid}/markup.bcf", ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return buf.getvalue()


def parse_records_bcfzip(data: bytes) -> list[dict]:
    """Parse a .bcfzip into record dicts {data:{subject,description,priority}, anchor, element_guids}
    suitable for creating module records. Pulls selected components + camera from any viewpoint."""
    out = []
    with _open_bcfzip(data) as z:
        names = z.namelist()
        for name in [n for n in names if n.endswith("markup.bcf")]:
            root = _safe_fromstring(z.read(name))
            te = root.find("Topic")
            if te is None:
                continue
            rec: dict[str, Any] = {"subject": te.findtext("Title") or "Imported issue",
                                   "description": te.findtext("Description"),
                                   "priority": te.findtext("Priority")}
            folder = name.rsplit("/", 1)[0] if "/" in name else ""
            comps: list[str] = []
            anchor = None
            for vp in [n for n in names if n.endswith(".bcfv") and (not folder or n.startswith(folder + "/"))]:
                vroot = _safe_fromstring(z.read(vp))
                for comp in vroot.findall(".//Selection/Component"):
                    g = comp.get("IfcGuid")
                    if g:
                        comps.append(g)
                cam = _parse_camera(vroot)
                if cam is not None:
                    anchor = cam.get("position")
            out.append({"data": {k: v for k, v in rec.items() if v is not None},
                        "anchor": anchor, "element_guids": comps,
                        "status": te.get("TopicStatus")})
    return out


def import_bcfzip(db: Session, project_id: str, data: bytes) -> int:
    """Import topics from a .bcfzip. Returns the count imported."""
    count = 0
    with _open_bcfzip(data) as z:
        names = z.namelist()
        markups = [n for n in names if n.endswith("markup.bcf")]
        for name in markups:
            root = _safe_fromstring(z.read(name))
            te = root.find("Topic")
            if te is None:
                continue
            # restore the pin (selected components by IFC GUID + camera) from any viewpoint in the folder
            folder = name.rsplit("/", 1)[0] if "/" in name else ""
            comps: list[str] = []
            anchor = None
            cam = None
            coloring: list = []
            for vp in [n for n in names if n.endswith(".bcfv") and (not folder or n.startswith(folder + "/"))]:
                vroot = _safe_fromstring(z.read(vp))
                for comp in vroot.findall(".//Selection/Component"):
                    g = comp.get("IfcGuid")
                    if g:
                        comps.append(g)
                cam = _parse_camera(vroot) or cam
                coloring = _parse_coloring(vroot) or coloring
                if cam is not None:
                    anchor = cam.get("position")
            topic = Topic(
                project_id=project_id,
                guid=te.get("Guid"),
                type=te.get("TopicType", "info"),
                status=te.get("TopicStatus", "open"),
                title=(te.findtext("Title") or "Imported topic"),
                description=te.findtext("Description"),
                priority=te.findtext("Priority"),
                assignee=te.findtext("AssignedTo"),
                author=te.findtext("CreationAuthor"),
                labels=_all_labels(te),
                element_guids=comps or None,
                anchor=anchor,
            )
            for ce in _all_comments(root, te):
                topic.comments.append(Comment(
                    author=ce.findtext("Author"),
                    text=ce.findtext("Comment") or "",
                ))
            # preserve the full camera (incl. orthographic) + per-element coloring as a Viewpoint,
            # so a section/coloured viewpoint from Solibri/ACC survives the round-trip (not just the pin).
            if cam is not None or coloring:
                topic.viewpoints.append(Viewpoint(
                    camera=cam, components=comps or None,
                    visibility={"coloring": coloring} if coloring else None))
            db.add(topic)
            count += 1
    return count
