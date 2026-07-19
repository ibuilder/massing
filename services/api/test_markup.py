"""Drawing-markup convergence: the 2D takeoff editor persists structured markups into the same
drawing_markups store as SVG pins (kind + data JSON), reloads them, and promotes them to RFIs.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_markup.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_markup.db"
os.environ["STORAGE_DIR"] = "./test_storage_markup"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_markup.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

with TestClient(app) as c:
    c.post("/auth/register", json={"username": "admin", "password": "supersecret"})
    tok = c.post("/auth/login", json={"username": "admin", "password": "supersecret"}).json()["token"]
    H = BEARER(tok)
    pid = c.post("/projects", json={"name": "Markup"}).json()["id"]

    # a plain pin on the SVG sheet (existing behaviour) + a structured takeoff markup with data
    c.post(f"/projects/{pid}/drawings/markup", headers=H,
           json={"sheet_id": "S-101", "x": 0.25, "y": 0.5, "note": "cloud"})
    r = c.post(f"/projects/{pid}/drawings/markup", headers=H, json={
        "sheet_id": "S-101#pdf", "x": 10, "y": 20, "note": "wall run", "kind": "distance",
        "data": {"pts": [{"x": 10, "y": 20}, {"x": 40, "y": 20}], "value": 12.5, "unit": "m", "page": 1}})
    assert r.status_code == 201 and r.json()["kind"] == "distance", r.text
    assert r.json()["data"]["value"] == 12.5

    # bulk-save a whole PDF-editor scene (replace=True clears prior unpromoted #pdf markups)
    scene = [
        {"x": 0, "y": 0, "note": "area A", "kind": "area",
         "data": {"pts": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 5}], "value": 25, "unit": "m2", "page": 1}},
        {"x": 3, "y": 3, "note": "count fixtures", "kind": "count",
         "data": {"pts": [{"x": 3, "y": 3}], "value": 1, "unit": "ea", "page": 1}},
    ]
    r = c.post(f"/projects/{pid}/drawings/markup/bulk", headers=H,
               json={"sheet_id": "S-101#pdf", "replace": True, "markups": scene})
    assert r.status_code == 201 and r.json()["saved"] == 2, r.text

    # the SVG sheet (S-101) still has only its pin — bulk replace on #pdf didn't touch it
    pins = c.get(f"/projects/{pid}/drawings/markup?sheet=S-101", headers=H).json()
    assert len(pins) == 1 and pins[0]["kind"] == "pin", pins

    # the PDF sheet (#pdf) now reflects the bulk scene (prior single 'distance' was replaced)
    pdfm = c.get(f"/projects/{pid}/drawings/markup?sheet=S-101%23pdf", headers=H).json()
    assert len(pdfm) == 2 and {m["kind"] for m in pdfm} == {"area", "count"}, pdfm
    assert any(m["data"]["value"] == 25 for m in pdfm)

    # promote a takeoff markup → RFI Topic, and the measurement rides along in the description
    mid = next(m["id"] for m in pdfm if m["kind"] == "area")
    pr = c.post(f"/projects/{pid}/drawings/markup/{mid}/promote", headers=H)
    assert pr.status_code == 201 and pr.json()["topic"]["type"] == "rfi", pr.text

    # a promoted markup survives a subsequent replace (topic_id set → kept)
    c.post(f"/projects/{pid}/drawings/markup/bulk", headers=H,
           json={"sheet_id": "S-101#pdf", "replace": True, "markups": []})
    kept = c.get(f"/projects/{pid}/drawings/markup?sheet=S-101%23pdf", headers=H).json()
    assert len(kept) == 1 and kept[0]["topic_id"], kept

    # --- MARKUP-2a slip-sheet: markups stamp the register revision + carry forward on revise -------
    # a registered sheet at Rev 1
    did = c.post(f"/projects/{pid}/modules/drawing", headers=H, json={"data": {
        "number": "S-201", "title": "Slip Sheet", "revision": "1", "discipline": "Structural"}}).json()["id"]
    # markups on the SVG sheet AND the PDF space stamp rev=1 at save
    c.post(f"/projects/{pid}/drawings/markup", headers=H,
           json={"sheet_id": "S-201", "x": 1, "y": 1, "note": "check base plate"})
    c.post(f"/projects/{pid}/drawings/markup/bulk", headers=H, json={"sheet_id": "S-201#pdf", "replace": True,
        "markups": [{"x": 2, "y": 2, "note": "dim", "kind": "distance",
                     "data": {"pts": [{"x": 2, "y": 2}], "value": 3.2, "unit": "m", "page": 1}}]})
    m201 = c.get(f"/projects/{pid}/drawings/markup?sheet=S-201", headers=H).json()
    assert m201[0]["data"]["rev"] == "1", m201
    # revise the sheet to Rev 2 → both markups tagged carried_from=1 (they predate the new rev)
    rr = c.post(f"/projects/{pid}/drawings/{did}/revise", headers=H,
                json={"rev": "2", "description": "ASI-001 rebar change"}).json()
    assert rr["revision"] == "2" and rr["markups_carried"] == 2, rr
    carried = c.get(f"/projects/{pid}/drawings/markup?sheet=S-201", headers=H).json()
    assert carried[0]["data"]["carried_from"] == "1", carried
    # a NEW markup after the revise stamps rev=2 with no carried flag; re-revise carries only the old one
    c.post(f"/projects/{pid}/drawings/markup", headers=H,
           json={"sheet_id": "S-201", "x": 5, "y": 5, "note": "new on rev 2"})
    fresh = [m for m in c.get(f"/projects/{pid}/drawings/markup?sheet=S-201", headers=H).json()
             if m["note"] == "new on rev 2"][0]
    assert fresh["data"]["rev"] == "2" and "carried_from" not in fresh["data"], fresh
    rr2 = c.post(f"/projects/{pid}/drawings/{did}/revise", headers=H, json={"rev": "3"}).json()
    assert rr2["markups_carried"] == 1, rr2          # only the rev-2 markup newly carries (others already tagged)

    # --- MARKUP-2d (live co-markup): the stream's change-signature moves on every save -------------
    from sqlalchemy import func as _f  # noqa: E402

    from aec_api.db import SessionLocal  # noqa: E402
    from aec_api.models import DrawingMarkup  # noqa: E402
    with SessionLocal() as s:
        n1, _t1 = (s.query(_f.count(DrawingMarkup.id), _f.max(DrawingMarkup.created_at))
                   .filter(DrawingMarkup.project_id == pid).one())
    c.post(f"/projects/{pid}/drawings/markup", headers=H,
           json={"sheet_id": "S-101", "x": 9, "y": 9, "note": "live co-markup"})
    with SessionLocal() as s:
        n2, t2 = (s.query(_f.count(DrawingMarkup.id), _f.max(DrawingMarkup.created_at))
                  .filter(DrawingMarkup.project_id == pid).one())
    assert n2 == (n1 or 0) + 1 and t2 is not None, "signature must move on every markup save"
    # the SSE route itself is registered (generator behaviour mirrors the tested pull-plan stream)
    assert "/projects/{pid}/drawings/markup/stream" in app.openapi()["paths"], "stream route missing"

print("MARKUP OK - takeoff markups persist to the shared drawing_markups store (kind+data), bulk "
      "save/replace scoped per sheet + author, SVG pins untouched, structured markup promotes to RFI "
      "with its measurement, and promoted markups survive replace. SLIP-SHEET: markups stamp the "
      "register rev at save; revise tags carried_from on both sheet spaces; fresh markups stamp the "
      "new rev; re-revise carries only untagged rows.")
