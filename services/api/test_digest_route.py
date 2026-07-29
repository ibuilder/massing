"""R23-DIGEST over HTTP — the engine is tested in `test_model_digest.py`; this asserts there is a
**path to it**.

Seven of eleven things built in one sprint shipped with no route: every gate measured the module and
none measured the way in. So this test does not re-test the digest. It asserts the two endpoints
answer 200 on a live app, that the round trip a caller actually performs — GET a digest, keep it,
POST it back after a change — reports that change, and that the configuration guard survives the
serialize/deserialize trip through JSON (it is enforced on `mode`, and `mode` has to come back
across the wire intact for the guard to mean anything).

Asserted through `with TestClient(app)` on purpose: routers are included lazily in the lifespan, so
inspecting `app.routes` at import time reports every endpoint as missing.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_digest_route.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_digest_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_digest_route"
os.environ["IFC_DIR"] = "./test_ifc_digest_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_digest_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

import ifcopenshell  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_data import edit as edit_mod  # noqa: E402
from aec_data import edit_struct, massing  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


tmp = Path(tempfile.gettempdir())
v1 = tmp / "digest_route_v1.ifc"
massing.generate_blank_ifc(str(v1), name="Digest Route", storeys=2, storey_height=3.5)
m = ifcopenshell.open(str(v1))
wall = edit_struct.add_wall(m, (0.0, 0.0), (6.0, 0.0), height=3.0, storey="Level 1")
edit_struct.add_column(m, (2.0, 2.0), height=3.0, storey="Level 2")
m.write(str(v1))

# v2 — the same building, republished with one wall moved and one column added.
v2 = tmp / "digest_route_v2.ifc"
v2.write_bytes(v1.read_bytes())
m2 = ifcopenshell.open(str(v2))
edit_mod.move_element(m2, wall, dx=2.0)
added = edit_struct.add_column(m2, (5.0, 2.0), height=3.0, storey="Level 2")
m2.write(str(v2))

with TestClient(app) as c:
    c.headers.update({"X-User": "digest@test"})
    pid = c.post("/projects", json={"name": "Digest Route"}).json()["id"]

    # A project with no model must 409, not 500 — the same contract every other analysis route holds.
    pre = c.get(f"/projects/{pid}/digest")
    check("no source IFC → a 4xx, not a 500", 400 <= pre.status_code < 500, pre.status_code)

    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("model.ifc", v1.read_bytes(), "application/octet-stream")})
    check("v1 uploads", up.status_code == 200, up.text[:160])

    r = c.get(f"/projects/{pid}/digest")
    check("GET /projects/{pid}/digest answers 200", r.status_code == 200, r.text[:200])
    full = r.json()
    check("  it is a digest", full.get("digest_version") == 1 and "tree" in full)
    check("  the tree carries a hash", bool(full["tree"].get("hash")))

    s = c.get(f"/projects/{pid}/digest?summary=true").json()
    check("summary=true returns the one-screen form",
          set(s) >= {"hash", "elements", "storeys", "mode"} and "tree" not in s, sorted(s))
    check("  the summary hash matches the full digest's", s["hash"] == full["tree"]["hash"])

    baseline = c.get(f"/projects/{pid}/digest?scale=storey").json()
    check("scale=storey prunes", baseline["mode"]["pruned_at"] == "storey")
    check("  and keeps the hash the full digest had",
          baseline["tree"]["hash"] == full["tree"]["hash"])

    bad = c.get(f"/projects/{pid}/digest?scale=floor")
    check("an unknown scale is rejected by the route", bad.status_code == 422, bad.status_code)

    # --- the actual loop: keep a digest, republish, post the digest back ------------------------
    same = c.post(f"/projects/{pid}/digest/diff", json=full)
    check("POST /projects/{pid}/digest/diff answers 200", same.status_code == 200, same.text[:200])
    body = same.json()
    check("  an unchanged model diffs as identical", body["diff"]["identical"] is True, body["diff"])

    up2 = c.post(f"/projects/{pid}/source-ifc?publish=false",
                 files={"file": ("model.ifc", v2.read_bytes(), "application/octet-stream")})
    check("v2 uploads over v1", up2.status_code == 200, up2.text[:160])

    d = c.post(f"/projects/{pid}/digest/diff", json=full).json()["diff"]
    check("the republished model is not identical", d["identical"] is False)
    check("  the moved wall is reported changed on origin",
          [(x["guid"], x["fields"]) for x in d["elements"]["changed"]] == [(wall, ["origin"])],
          d["elements"]["changed"])
    check("  the new column is reported added",
          [a["guid"] for a in d["elements"]["added"]] == [added], d["elements"]["added"])
    check("  nothing is reported removed", d["elements"]["removed"] == [])

    # A pruned baseline still answers at storey level, and says what it did not compare.
    dp = c.post(f"/projects/{pid}/digest/diff", json=baseline).json()["diff"]
    check("a pruned baseline is compatible", dp["compatible"] is True, dp.get("reason"))
    check("  it names the changed storeys",
          set(dp["storeys"]["changed"]) == {"Level 1", "Level 2"}, dp["storeys"])
    check("  and states that elements were not compared",
          dp["elements"] is None and dp.get("elements_not_compared"))

    # --- the configuration guard, over the wire ------------------------------------------------
    # The guard lives on `mode`, and `mode` has to survive JSON intact for it to guard anything.
    # This also pins the route's deliberate refusal to inherit the baseline's *measurement* mode:
    # if it did, a string in caller-supplied JSON would decide whether this request meshes every
    # element in the model, and the guard would never fire because the two sides would always agree.
    forged = {**full, "mode": {**full["mode"], "measured": "psets+geometry"}}
    g = c.post(f"/projects/{pid}/digest/diff", json=forged).json()["diff"]
    check("a cross-mode baseline is refused over the wire", g["compatible"] is False, g.get("reason"))
    check("  with a stated reason", "geometry-derived" in (g.get("reason") or ""), g.get("reason"))
    check("  and it did NOT quietly mesh the model to make itself agree",
          g.get("elements") is None and "identical" in g)

    # A scale the engine does not know must not reach the engine as a prune argument.
    bogus = c.post(f"/projects/{pid}/digest/diff",
                   json={**full, "mode": {**full["mode"], "pruned_at": "floor"}})
    check("a baseline with an unknown scale is a 422, not a 500", bogus.status_code == 422,
          bogus.status_code)

    junk = c.post(f"/projects/{pid}/digest/diff", json={"hello": "world"})
    check("a non-digest baseline is a 422, not a 500", junk.status_code == 422, junk.status_code)

print()
if FAILED:
    print(f"digest_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("digest_route: all checks passed")
