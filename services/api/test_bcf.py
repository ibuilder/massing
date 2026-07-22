"""BCF 2.1 round-trip (a CLAUDE.md non-negotiable: pins/RFIs follow the BCF model so they round-trip
with other BIM tools). Covers the project-Topic path (export -> import into a fresh project) and the
config-module records path (export_records -> parse_records), incl. viewpoints/components by GUID.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bcf.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bcf.db"
os.environ["STORAGE_DIR"] = "./test_storage_bcf"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_bcf.db",):
    if os.path.exists(f):
        os.remove(f)

import io  # noqa: E402
import zipfile  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import bcf_io  # noqa: E402
from aec_api.main import app  # noqa: E402

GUID = "3vB2eYHr1ABcDeFgHiJkLm"          # an IFC GlobalId on the topic's viewpoint


with TestClient(app) as c:
    src = c.post("/projects", json={"name": "BCF Source"}).json()["id"]

    # a pinned clash topic (element-tied) + a plain RFI topic
    t1 = c.post(f"/projects/{src}/topics", json={
        "type": "clash", "title": "Beam vs duct", "description": "HVAC main clips the W21",
        "priority": "High", "assignee": "coordinator", "labels": ["CLH-001"],
        "anchor": {"x": 12.5, "y": 3.0, "z": 4.2}, "element_guids": [GUID]})
    assert t1.status_code == 201, t1.text[:200]
    c.post(f"/projects/{src}/topics", json={"type": "rfi", "title": "Slab edge detail"})

    # --- project Topic path: export .bcfzip -> import into a FRESH project ----
    exp = c.get(f"/projects/{src}/bcf/export")
    assert exp.status_code == 200, exp.text[:200]
    blob = exp.content
    # it's a real BCF zip: bcf.version + per-topic markup.bcf + a viewpoint for the pinned one
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        assert "bcf.version" in names, names
        assert sum(1 for n in names if n.endswith("markup.bcf")) == 2, names
        assert any(n.endswith(".bcfv") for n in names), names      # pinned topic carries a viewpoint

    dst = c.post("/projects", json={"name": "BCF Target"}).json()["id"]
    imp = c.post(f"/projects/{dst}/bcf/import",
                 files={"file": ("issues.bcfzip", blob, "application/zip")})
    assert imp.status_code == 200, imp.text[:200]
    assert imp.json()["imported"] == 2, imp.json()

    topics = c.get(f"/projects/{dst}/topics").json()
    assert len(topics) == 2, topics
    # PERF-4: the topics list is paginated (default 500, hard cap) — limit/offset bound the payload
    assert len(c.get(f"/projects/{dst}/topics?limit=1").json()) == 1, "limit caps the page"
    assert len(c.get(f"/projects/{dst}/topics?offset=1").json()) == 1, "offset skips"
    assert len(c.get(f"/projects/{dst}/topics?limit=99999").json()) == 2, "over-cap limit is clamped, not an error"
    # HARDEN-2 (B1): the cap keeps the NEWEST rows — a limited page must contain the latest topic,
    # not the oldest (the old asc+limit silently hid everything created after row N).
    newest_id = topics[-1]["id"]                     # full list is ascending; last = newest
    assert c.get(f"/projects/{dst}/topics?limit=1").json()[0]["id"] == newest_id, "cap must keep newest"
    titles = {t["title"] for t in topics}
    assert {"Beam vs duct", "Slab edge detail"} == titles, titles
    clash = next(t for t in topics if t["title"] == "Beam vs duct")
    assert clash["description"] == "HVAC main clips the W21", clash
    assert clash["priority"] == "High", clash
    # the pin survives: element tie by IFC GlobalId + the 3D anchor (non-negotiable)
    assert clash["element_guids"] == [GUID], clash
    assert clash["anchor"] and abs(clash["anchor"]["x"] - 12.5) < 1e-6, clash

    # --- config-module records path: export_records -> parse_records ----------
    records = [{
        "id": "rec-guid-1", "ref": "CI-001", "title": "Sprinkler vs beam",
        "workflow_state": "open", "assignee": "qa",
        "data": {"subject": "Sprinkler vs beam", "description": "Branch line below structure",
                 "priority": "Critical"},
        "element_guids": [GUID], "anchor": {"x": 1.0, "y": 2.0, "z": 3.0}}]
    z_bytes = bcf_io.export_records_bcfzip(records, topic_type="Clash")
    parsed = bcf_io.parse_records_bcfzip(z_bytes)
    assert len(parsed) == 1, parsed
    p = parsed[0]
    assert p["data"]["subject"] == "Sprinkler vs beam", p
    assert p["data"]["priority"] == "Critical", p
    assert GUID in p["element_guids"], p                        # component round-trips by IFC GUID
    assert p["anchor"] and abs(p["anchor"]["x"] - 1.0) < 1e-6, p
    assert p["status"] == "open", p

    # --- viewpoint fidelity: full camera (persp + ortho) + per-element coloring ----
    import xml.etree.ElementTree as ET  # noqa: E402

    from aec_api.models import Viewpoint  # noqa: E402

    # perspective: position + target -> direction is derived + normalized; fov + up survive
    vp = Viewpoint(guid="vp-p", components=[GUID],
                   camera={"type": "perspective", "position": {"x": 0, "y": 0, "z": 0},
                           "target": {"x": 0, "y": 0, "z": -5}, "fov": 45, "up": {"x": 0, "y": 1, "z": 0}},
                   visibility={"default_visibility": True, "coloring": [{"color": "FF0000", "guids": [GUID]}]})
    root = ET.fromstring(bcf_io._viewpoint_xml(vp))
    cam = bcf_io._parse_camera(root)
    assert cam["type"] == "perspective" and cam["fov"] == 45.0, cam
    assert abs(cam["direction"]["z"] + 1.0) < 1e-6, cam           # (0,0,-5) normalized -> (0,0,-1)
    assert cam["up"] == {"x": 0.0, "y": 1.0, "z": 0.0}, cam
    coloring = bcf_io._parse_coloring(root)
    assert coloring == [{"color": "FF0000", "guids": [GUID]}], coloring   # per-element colour survives

    # orthographic (section/elevation): type + ViewToWorldScale survive
    vpo = Viewpoint(guid="vp-o", camera={"type": "orthographic", "position": {"x": 1, "y": 2, "z": 3},
                                         "direction": {"x": 0, "y": 0, "z": -1}, "view_to_world_scale": 42.0})
    camo = bcf_io._parse_camera(ET.fromstring(bcf_io._viewpoint_xml(vpo)))
    assert camo["type"] == "orthographic" and camo["view_to_world_scale"] == 42.0, camo
    assert camo["position"] == {"x": 1.0, "y": 2.0, "z": 3.0}, camo

    # end-to-end: a crafted external BCF with an OrthogonalCamera imports (proves the real import path)
    vbytes = (b'<?xml version="1.0"?><VisualizationInfo><OrthogonalCamera>'
              b'<CameraViewPoint><X>7</X><Y>8</Y><Z>9</Z></CameraViewPoint>'
              b'<CameraDirection><X>0</X><Y>0</Y><Z>-1</Z></CameraDirection>'
              b'<CameraUpVector><X>0</X><Y>1</Y><Z>0</Z></CameraUpVector>'
              b'<ViewToWorldScale>10</ViewToWorldScale></OrthogonalCamera></VisualizationInfo>')
    mbytes = (b'<?xml version="1.0"?><Markup><Topic Guid="ortho-1" TopicType="clash" TopicStatus="open">'
              b'<Title>Section view clash</Title></Topic></Markup>')
    obuf = io.BytesIO()
    with zipfile.ZipFile(obuf, "w") as z:
        z.writestr("bcf.version", b'<?xml version="1.0"?><Version VersionId="2.1"/>')
        z.writestr("ortho-1/markup.bcf", mbytes)
        z.writestr("ortho-1/ortho-1.bcfv", vbytes)
    dst2 = c.post("/projects", json={"name": "BCF Ortho"}).json()["id"]
    io2 = c.post(f"/projects/{dst2}/bcf/import", files={"file": ("o.bcfzip", obuf.getvalue(), "application/zip")})
    assert io2.status_code == 200 and io2.json()["imported"] == 1, io2.text[:200]
    ot = c.get(f"/projects/{dst2}/topics").json()[0]
    assert ot["anchor"]["x"] == 7.0 and ot["anchor"]["z"] == 9.0, ot   # ortho camera position -> anchor

    # --- BCF 3.0: export emits the 3.0 shape; import reads it (incl. the 3.0-only locations) ------
    exp3 = c.get(f"/projects/{src}/bcf/export?version=3.0")
    assert exp3.status_code == 200, exp3.text[:200]
    blob3 = exp3.content
    with zipfile.ZipFile(io.BytesIO(blob3)) as z:
        assert 'VersionId="3.0"' in z.read("bcf.version").decode(), "version file says 3.0"
        pinned = next(n for n in z.namelist() if n.endswith("markup.bcf") and b"Beam vs duct" in z.read(n))
        mroot = ET.fromstring(z.read(pinned))
        # 3.0 nests Viewpoints under <Topic> and groups <Labels><Label>; no 2.1-style sibling Viewpoints
        assert mroot.find("Topic/Viewpoints/ViewPoint") is not None, "3.0 nests Viewpoints under Topic"
        assert mroot.find("Topic/Labels/Label") is not None, "3.0 groups Labels/Label"
        assert mroot.find("Viewpoints") is None, "no 2.1 sibling <Viewpoints> in a 3.0 markup"
    # re-import the 3.0 file into a fresh project -> the 2 topics + the pin survive
    dst3 = c.post("/projects", json={"name": "BCF 3.0 Target"}).json()["id"]
    imp3 = c.post(f"/projects/{dst3}/bcf/import", files={"file": ("v3.bcfzip", blob3, "application/zip")})
    assert imp3.status_code == 200 and imp3.json()["imported"] == 2, imp3.text[:200]
    clash3 = next(t for t in c.get(f"/projects/{dst3}/topics").json() if t["title"] == "Beam vs duct")
    assert clash3["element_guids"] == [GUID] and clash3["priority"] == "High", clash3

    # a crafted external 3.0 file (grouped labels + a comment nested under <Topic><Comments>) imports:
    # this exercises the 3.0-only read paths (_all_labels / _all_comments) directly against the engine.
    m3 = (b'<?xml version="1.0"?><Markup><Topic Guid="v3-1" TopicType="clash" TopicStatus="open">'
          b'<Title>3.0 nested</Title><Labels><Label>NC-9</Label></Labels>'
          b'<Comments><Comment Guid="cc1"><Author>qa</Author><Comment>please fix</Comment></Comment>'
          b'</Comments></Topic></Markup>')
    b3buf = io.BytesIO()
    with zipfile.ZipFile(b3buf, "w") as z:
        z.writestr("bcf.version", b'<?xml version="1.0"?><Version VersionId="3.0"/>')
        z.writestr("v3-1/markup.bcf", m3)
    from aec_api.db import SessionLocal  # noqa: E402
    from aec_api.models import Topic as _Topic  # noqa: E402
    p3 = c.post("/projects", json={"name": "BCF 3.0 nested"}).json()["id"]
    with SessionLocal() as db:
        assert bcf_io.import_bcfzip(db, p3, b3buf.getvalue()) == 1
        db.commit()
        topic = db.query(_Topic).filter(_Topic.project_id == p3).first()
        assert topic.labels == ["NC-9"], topic.labels               # grouped <Labels><Label> read
        assert topic.comments and topic.comments[0].text == "please fix", topic.comments  # nested comment read

    # --- SEC F9: decompression-bomb bounds — oversized uncompressed entries are rejected ----------
    from fastapi import HTTPException as _HTTPExc  # noqa: E402

    # a highly-compressible entry: ~2 MB of zeros -> tiny on disk, but declared file_size is real
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bcf.version", b'<?xml version="1.0"?><Version VersionId="2.1"/>')
        z.writestr("big/markup.bcf", b"\x00" * (2 * 1024 * 1024))
    orig_limit = bcf_io._MAX_UNZIP_BYTES
    try:
        bcf_io._MAX_UNZIP_BYTES = 1024                       # 1 KB ceiling for the test
        threw = False
        try:
            bcf_io.import_bcfzip(SessionLocal(), src, bomb.getvalue())
        except _HTTPExc as e:
            threw = True
            assert e.status_code == 413, e.status_code       # Payload Too Large, clear rejection
        assert threw, "oversized zip entry must be rejected"
        # parse_records_bcfzip shares the same guard
        threw2 = False
        try:
            bcf_io.parse_records_bcfzip(bomb.getvalue())
        except _HTTPExc as e:
            threw2 = True and e.status_code == 413
        assert threw2, "parse_records must also reject the bomb"
    finally:
        bcf_io._MAX_UNZIP_BYTES = orig_limit
    # under the (restored) real 512 MB limit, a normal small bcfzip still imports fine
    assert bcf_io.parse_records_bcfzip(blob) is not None, "normal bcfzip still parses under the limit"

    # empty project still exports a valid (topic-less) bcfzip — no crash
    empty = c.post("/projects", json={"name": "Empty"}).json()["id"]
    e = c.get(f"/projects/{empty}/bcf/export")
    assert e.status_code == 200
    with zipfile.ZipFile(io.BytesIO(e.content)) as z:
        assert "bcf.version" in z.namelist()
        assert not [n for n in z.namelist() if n.endswith("markup.bcf")]

print("BCF OK - Topic export/import round-trips into a fresh project (2 topics, fields + priority); "
      "module records export/parse preserve subject/priority/anchor + components by IFC GUID; "
      "BCF 3.0 export nests Viewpoints/Labels under <Topic> and re-imports, and a crafted 3.0 file's "
      "grouped labels + nested comments are read; empty project exports a valid topic-less bcfzip")
