"""R23-STOREY-LOD — the proxy generator, and the ways a coarse stand-in goes quietly wrong.

The saving is easy to demonstrate. These assertions are about the four ways a proxy misleads:

1. **an invisible proxy.** `_rect_profile`'s own docstring warns that web-ifc silently skips an element
   whose profile has no Position — it renders nothing, reports nothing, and the "LOD" is simply
   missing geometry. A proxy nobody can see is the same as no proxy, and nothing would say so;
2. **a proxy that does not declare itself.** A coarse box mistaken for authored geometry gets
   measured, scheduled and priced. It carries a name prefix AND a pset, so the fact survives whichever
   one a reader happens to look at;
3. **an empty export that reads as success** — a written file with no content is worse than a refusal;
4. **a zero-extent box at the origin** for a storey with nothing on it, which implies content that is
   not there.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_lod_proxy.py
"""
import os
import sys
import tempfile

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

import ifcopenshell  # noqa: E402
import ifcopenshell.geom as geom  # noqa: E402
import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import lod, massing  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 1. a real model, a real proxy ------------------------------------------------------------------
SRC = "../../samples/school_str.ifc"
have_src = os.path.exists(SRC)
check("the sample model this suite measures against is present", have_src,
      f"{SRC} missing — the assertions below would be vacuous")

if have_src:
    model = ifcopenshell.open(SRC)
    # mkdtemp, not mktemp: mktemp returns a name without creating it, so CodeQL rightly flags the
    # create-after-name race (py/insecure-temporary-file). Matches the fix applied to test_stair_ramp.
    out = os.path.join(tempfile.mkdtemp(prefix="lod_proxy_"), "proxy.ifc")
    rep = lod.build_storey_proxy(model, out)

    check("a proxy is written for a model full of rebar", rep["written"] is True, rep.get("reason"))
    check("  it replaces every reinforcing bar in the model",
          rep["elements_replaced"] == 619, rep["elements_replaced"])
    check("  across the storeys that actually carry them",
          rep["storeys_proxied"] == 2, rep["storeys_proxied"])

    proxy = ifcopenshell.open(out)
    boxes = proxy.by_type("IfcBuildingElementProxy")
    check("one box per storey, not one per element", len(boxes) == 2, len(boxes))

    # THE INVISIBLE-PROXY TRAP — the failure mode with no symptom.
    settings = geom.settings()
    tris = 0
    for b in boxes:
        # BIND the shape. `len(create_shape(...).geometry.faces)` chains off a temporary whose
        # buffer is released before `.faces` is read, and returns **0** — which here reads exactly
        # like the invisible-proxy defect this assertion exists to catch. It cost a false FAIL on
        # working code, and would have cost a false PASS if the polarity were reversed. Same family
        # as a detached ArrayBuffer reporting a zero-length payload.
        shape = geom.create_shape(settings, b)
        tris += len(shape.geometry.faces) // 3
    check("THE PROXY HAS GEOMETRY — a null profile Position renders it invisible and reports nothing",
          tris > 0, f"{tris} triangles: web-ifc would skip these silently")
    check("  and it is genuinely coarse — 12 triangles a box, against 189,508 for the rebar",
          tris <= 24 * len(boxes), tris)

    # DECLARES ITSELF, twice over.
    check("every proxy is NAMED as a proxy", all(b.Name.startswith(lod.PROXY_NAME_PREFIX) for b in boxes),
          [b.Name for b in boxes])
    ps = ue.get_psets(boxes[0]).get(lod.PROXY_PSET) or {}
    check("  and carries the AEC_LOD pset, so the fact survives either reader", ps.get("IsProxy") is True, ps)
    check("  naming the classes it stands in for", ps.get("ReplacesClasses") == "IfcReinforcingBar", ps)
    check("  and how many elements it replaced", int(ps.get("ReplacesElementCount", 0)) > 0, ps)
    check("  with a note telling a downstream tool NOT to measure or price it",
          "do not measure" in (ps.get("Note") or ""), ps.get("Note"))

    check("each proxied storey reports its bounds, so the box can be checked",
          all("bbox" in r for r in rep["storeys"] if r["proxied"]), rep["storeys"])
    os.unlink(out)

# --- 2. nothing to proxy is a REFUSAL, not an empty file ------------------------------------------------
_d = tempfile.mkdtemp(prefix="lod_blank_")
blank = os.path.join(_d, "blank.ifc")
massing.generate_blank_ifc(blank, name="Empty", storeys=2, storey_height=3.5)
bm = ifcopenshell.open(blank)
out2 = os.path.join(_d, "proxy_out.ifc")
r2 = lod.build_storey_proxy(bm, out2)
check("a model with no proxyable class writes NO file", r2["written"] is False, r2)
check("  and says so rather than exporting an empty model that looks successful",
      "successful export" in r2["reason"], r2["reason"])
check("  and no file was actually created", not os.path.exists(out2), out2)
check("  the status is no_geometry, not a clean zero",
      r2["status"] == lod.STATUS_NO_GEOMETRY, r2["status"])

# --- 3. the class set is a policy, and structure stays out of it ------------------------------------------
if have_src:
    model2 = ifcopenshell.open(SRC)
    out3 = os.path.join(tempfile.mkdtemp(prefix="lod_none_"), "none.ifc")
    r3 = lod.build_storey_proxy(model2, out3, classes=("IfcDoor",))
    check("asking for a class the model lacks refuses rather than writing an empty proxy",
          r3["written"] is False, r3)
    if os.path.exists(out3):
        os.unlink(out3)

check("structure is not in the default proxy set",
      not (set(lod.STRUCTURAL_CLASSES) & set(lod.SMALL_PART_CLASSES)))
check("the proxy marker constants are exported so a reader can find them",
      lod.PROXY_PSET == "AEC_LOD" and lod.PROXY_NAME_PREFIX.startswith("LOD Proxy"))

# --- 4. THE ROUTES — because an engine nothing can call is the defect this repo keeps finding -------
# `test_reachable` scans `aec_api` only, so it is structurally unable to see an orphan in `aec_data`.
# lod.py was imported by nothing but its own tests until these landed. Asserted over HTTP, because a
# route in a file is not a route.
import os as _os  # noqa: E402

_os.environ["DATABASE_URL"] = "sqlite:///./test_lod_proxy_route.db"
_os.environ["STORAGE_DIR"] = "./test_storage_lod_proxy_route"
_os.environ.pop("AEC_RBAC", None)
for _f in ("./test_lod_proxy_route.db",):
    if _os.path.exists(_f):
        _os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as client:
    client.headers.update({"X-User": "lod@test"})
    pid = client.post("/projects", json={"name": "LOD"}).json()["id"]

    r = client.get(f"/projects/{pid}/model/lod/census")
    check("the census route 409s without a source model, rather than 500ing",
          r.status_code == 409, r.status_code)
    r = client.post(f"/projects/{pid}/model/lod/proxy", json={})
    check("  and so does the proxy route", r.status_code == 409, r.status_code)

    if have_src:
        with SessionLocal() as db:
            proj = db.get(Project, pid)
            proj.source_ifc = _os.path.abspath(SRC)
            db.commit()

        c = client.get(f"/projects/{pid}/model/lod/census?max_elements=800").json()
        check("the census route answers over HTTP", c["elements_examined"] == 800,
              c.get("elements_examined"))
        check("  it reports the cap it hit", c["capped"] is True, c)
        check("  and the PLAN marks its saving a lower bound, so a capped 0% is not read as a verdict",
              c["plan"]["saving_is_lower_bound"] is True, c["plan"])

        pr = client.post(f"/projects/{pid}/model/lod/proxy", json={}).json()
        check("the proxy route stores an artefact", pr.get("stored") is True, pr.get("reason"))
        check("  replacing every reinforcing bar", pr["elements_replaced"] == 619,
              pr["elements_replaced"])
        check("  and keys it beside the model", str(pr.get("key", "")).endswith("model.lod.ifc"),
              pr.get("key"))

print()
if FAILED:
    print(f"lod_proxy: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("lod_proxy: all checks passed")
