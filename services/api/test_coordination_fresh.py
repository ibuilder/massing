"""SMART-VIEWS clash freshness — flag open clash/coordination topics whose elements changed between
two model versions (advisory re-verify, never auto-close). Engine over injected ModelVersion rows +
the /coordination/stale + /recheck routes.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_coordination_fresh.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_coord_fresh.db"
os.environ["STORAGE_DIR"] = "./test_storage_coord_fresh"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_coord_fresh.db"):
    os.remove("./test_coord_fresh.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import ModelVersion  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Coord"}).json()["id"]

    # two versions: v1 has {g1,g2,g3}; v2 modifies g1 (fingerprint change) + removes g3 + adds g4
    # fingerprints are 6-tuples: [name, ifc_class, type_name, storey, pset_hash, qto_hash]
    def _fp(name, cls, ph):
        return [name, cls, "T", "L1", ph, "q"]
    with SessionLocal() as db:
        db.add(ModelVersion(project_id=pid, version=1, element_count=3, guids=["g1", "g2", "g3"],
                            fingerprints={"g1": _fp("W1", "IfcWall", "h1"), "g2": _fp("W2", "IfcWall", "h2"),
                                          "g3": _fp("P1", "IfcPipe", "h3")}, note="v1"))
        db.add(ModelVersion(project_id=pid, version=2, element_count=3, guids=["g1", "g2", "g4"],
                            fingerprints={"g1": _fp("W1", "IfcWall", "h1-CHANGED"),   # g1 pset changed → modified
                                          "g2": _fp("W2", "IfcWall", "h2"),           # g2 unchanged
                                          "g4": _fp("D1", "IfcDuct", "h4")}, note="v2"))
        db.commit()

    # three open clash topics: one on g1 (modified → stale), one on g3 (removed → stale),
    # one on g2 (unchanged → NOT stale); plus a non-clash topic on g1 (ignored)
    def _clash(guids, title, ttype="clash", status="open"):
        return c.post(f"/projects/{pid}/topics", json={
            "type": ttype, "status": status, "title": title, "element_guids": guids}).json()

    t_mod = _clash(["g1", "g99"], "Duct vs beam @g1")
    _clash(["g3"], "Pipe vs wall @g3")
    _clash(["g2"], "Rebar clash @g2")                       # unchanged element → not flagged
    _clash(["g1"], "RFI about g1", ttype="rfi")             # not a clash type → ignored
    _clash(["g1"], "Old resolved clash @g1", status="closed")   # closed → ignored

    # scan: which open clashes touch a changed element between v1→v2
    st = c.get(f"/projects/{pid}/coordination/stale?a=1&b=2").json()
    assert st["changed_elements"] == 3, st                  # g1(mod) + g3(removed) + g4(added)
    assert st["open_coordination_issues"] == 3, st          # 3 open CLASH topics (rfi/closed excluded)
    titles = {s["title"] for s in st["stale"]}
    assert titles == {"Duct vs beam @g1", "Pipe vs wall @g3"}, titles
    assert st["stale_count"] == 2, st
    mod = next(s for s in st["stale"] if s["title"] == "Duct vs beam @g1")
    assert mod["changed_guids"] == ["g1"] and mod["already_flagged"] is False, mod

    # recheck: flags each stale topic (label + comment), never closes, idempotent
    rc = c.post(f"/projects/{pid}/coordination/stale/recheck", json={"a": 1, "b": 2}).json()
    assert rc["flagged"] == 2, rc
    again = c.post(f"/projects/{pid}/coordination/stale/recheck", json={"a": 1, "b": 2}).json()
    assert again["flagged"] == 0, again                     # idempotent (already labelled)

    # the flagged topic carries the label + a comment, and is STILL open (never auto-closed)
    tt = c.get(f"/projects/{pid}/topics/{t_mod['id']}").json()
    assert "model-changed" in (tt["labels"] or []) and tt["status"] == "open", tt
    cm = c.get(f"/projects/{pid}/topics/{t_mod['id']}/comments").json()
    assert any("re-verify" in x["text"] for x in cm), cm

print("COORDINATION-FRESH OK - scan finds open clash topics whose elements changed v1→v2 (g1 modified, "
      "g3 removed → 2 stale; g2 unchanged, the rfi + closed topics excluded); recheck adds a "
      "model-changed label + a re-verify comment to each, is idempotent, and never auto-closes "
      "(topic stays open — the coordinator decides).")
