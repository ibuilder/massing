"""BCF .bcfzip import/export (guide §7).

A pragmatic subset of buildingSMART BCF 2.1: one folder per topic GUID containing
markup.bcf (topic + comments) and, when present, viewpoint.bcfv (camera + components).
This round-trips the spine that Solibri / ACC / BIMcollab read. Full BCF has more optional
fields; extend the XML builders/parsers as needed."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import Comment, Topic, Viewpoint

_BCF_VERSION = "2.1"


def _iso(dt: datetime | None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _markup_xml(topic: Topic) -> bytes:
    root = ET.Element("Markup")
    t = ET.SubElement(root, "Topic", {"Guid": topic.guid, "TopicType": topic.type, "TopicStatus": topic.status})
    ET.SubElement(t, "Title").text = topic.title or ""
    if topic.priority:
        ET.SubElement(t, "Priority").text = topic.priority
    if topic.assignee:
        ET.SubElement(t, "AssignedTo").text = topic.assignee
    if topic.description:
        ET.SubElement(t, "Description").text = topic.description
    ET.SubElement(t, "CreationDate").text = _iso(topic.created_at)
    if topic.author:
        ET.SubElement(t, "CreationAuthor").text = topic.author
    for label in topic.labels or []:
        ET.SubElement(t, "Labels").text = label

    for c in topic.comments:
        ce = ET.SubElement(root, "Comment", {"Guid": c.id})
        ET.SubElement(ce, "Date").text = _iso(c.created_at)
        if c.author:
            ET.SubElement(ce, "Author").text = c.author
        ET.SubElement(ce, "Comment").text = c.text
        if c.viewpoint_id:
            ET.SubElement(ce, "Viewpoint", {"Guid": c.viewpoint_id})

    for v in topic.viewpoints:
        vp = ET.SubElement(root, "Viewpoints", {"Guid": v.guid})
        ET.SubElement(vp, "Viewpoint").text = f"{v.guid}.bcfv"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _viewpoint_xml(v: Viewpoint) -> bytes:
    root = ET.Element("VisualizationInfo", {"Guid": v.guid})
    if v.components:
        comps = ET.SubElement(root, "Components")
        sel = ET.SubElement(comps, "Selection")
        for guid in v.components:
            ET.SubElement(sel, "Component", {"IfcGuid": guid})
    if v.visibility:
        comps = root.find("Components") or ET.SubElement(root, "Components")
        vis = ET.SubElement(comps, "Visibility",
                            {"DefaultVisibility": str(v.visibility.get("default_visibility", True)).lower()})
        exc = ET.SubElement(vis, "Exceptions")
        for guid in v.visibility.get("exceptions", []):
            ET.SubElement(exc, "Component", {"IfcGuid": guid})
    if v.camera:
        cam = v.camera
        pcam = ET.SubElement(root, "PerspectiveCamera")
        pos = cam.get("position", {})
        ET.SubElement(pcam, "CameraViewPoint")
        _xyz(pcam.find("CameraViewPoint"), pos)
        ET.SubElement(pcam, "FieldOfView").text = str(cam.get("fov", 60))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _xyz(parent: ET.Element, d: dict) -> None:
    ET.SubElement(parent, "X").text = str(d.get("x", 0))
    ET.SubElement(parent, "Y").text = str(d.get("y", 0))
    ET.SubElement(parent, "Z").text = str(d.get("z", 0))


def export_bcfzip(db: Session, project_id: str) -> bytes:
    topics = db.query(Topic).filter(Topic.project_id == project_id).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        bsmart = ET.Element("Version", {"VersionId": _BCF_VERSION})
        z.writestr("bcf.version", ET.tostring(bsmart, encoding="utf-8", xml_declaration=True))
        for topic in topics:
            z.writestr(f"{topic.guid}/markup.bcf", _markup_xml(topic))
            for v in topic.viewpoints:
                z.writestr(f"{topic.guid}/{v.guid}.bcfv", _viewpoint_xml(v))
    return buf.getvalue()


def _record_viewpoint_xml(guid: str, components: list[str], anchor: dict | None) -> bytes:
    root = ET.Element("VisualizationInfo", {"Guid": guid})
    if components:
        comps = ET.SubElement(root, "Components")
        sel = ET.SubElement(comps, "Selection")
        for g in components:
            ET.SubElement(sel, "Component", {"IfcGuid": g})
    if anchor:
        pcam = ET.SubElement(root, "PerspectiveCamera")
        ET.SubElement(pcam, "CameraViewPoint")
        _xyz(pcam.find("CameraViewPoint"), anchor)
        ET.SubElement(pcam, "FieldOfView").text = "60"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def export_records_bcfzip(records: list[dict], topic_type: str = "Issue") -> bytes:
    """Export config-module records (e.g. coordination_issue) as a BCF 2.1 .bcfzip so they round-trip
    with Solibri / ACC / BIMcollab. Each record → a topic (title/description/priority/status + ref as a
    label); a pinned/element-tied record also gets a viewpoint (selected components + camera at the pin)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bcf.version", ET.tostring(ET.Element("Version", {"VersionId": _BCF_VERSION}),
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
            if r.get("assignee"):
                ET.SubElement(t, "AssignedTo").text = str(r["assignee"])
            if data.get("description"):
                ET.SubElement(t, "Description").text = str(data["description"])
            ET.SubElement(t, "CreationDate").text = _iso(None)
            if r.get("ref"):
                ET.SubElement(t, "Labels").text = r["ref"]      # carry our ref so re-import can match
            comps = r.get("element_guids") or []
            anchor = r.get("anchor")
            if comps or anchor:
                ET.SubElement(root, "Viewpoints", {"Guid": guid}).append(ET.Element("Viewpoint"))
                root.find("Viewpoints/Viewpoint").text = f"{guid}.bcfv"
                z.writestr(f"{guid}/{guid}.bcfv", _record_viewpoint_xml(guid, comps, anchor))
            z.writestr(f"{guid}/markup.bcf", ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return buf.getvalue()


def parse_records_bcfzip(data: bytes) -> list[dict]:
    """Parse a .bcfzip into record dicts {data:{subject,description,priority}, anchor, element_guids}
    suitable for creating module records. Pulls selected components + camera from any viewpoint."""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        for name in [n for n in names if n.endswith("markup.bcf")]:
            root = ET.fromstring(z.read(name))
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
                vroot = ET.fromstring(z.read(vp))
                for comp in vroot.findall(".//Selection/Component"):
                    g = comp.get("IfcGuid")
                    if g:
                        comps.append(g)
                cvp = vroot.find("PerspectiveCamera/CameraViewPoint")
                if cvp is not None:
                    anchor = {ax.lower(): float(cvp.findtext(ax) or 0) for ax in ("X", "Y", "Z")}
            out.append({"data": {k: v for k, v in rec.items() if v is not None},
                        "anchor": anchor, "element_guids": comps,
                        "status": te.get("TopicStatus")})
    return out


def import_bcfzip(db: Session, project_id: str, data: bytes) -> int:
    """Import topics from a .bcfzip. Returns the count imported."""
    count = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        markups = [n for n in z.namelist() if n.endswith("markup.bcf")]
        for name in markups:
            root = ET.fromstring(z.read(name))
            te = root.find("Topic")
            if te is None:
                continue
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
                labels=[e.text for e in te.findall("Labels") if e.text],
            )
            for ce in root.findall("Comment"):
                topic.comments.append(Comment(
                    author=ce.findtext("Author"),
                    text=ce.findtext("Comment") or "",
                ))
            db.add(topic)
            count += 1
    return count
