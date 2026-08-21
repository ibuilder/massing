"""R43-VIEWER-CONFORMANCE — the two endpoints the conformance run found ABSENT.

`GET /projects/{pid}/spatial-tree` and `POST /projects/{pid}/elements/properties`. Both are called
by MassingViewer's `RemoteKernel`; neither existed, and the 2026-08-13 run recorded them as the only
two outright gaps among the endpoints it probed.

**The run's own record was wrong twice, and both corrections are asserted here rather than argued.**

1.  `elements/properties` is a **POST**, not a GET. The report probed it with GET, got
    `404 {"detail":"element not found"}` from `/elements/{guid}` matching with `guid="properties"`,
    and filed it as an absent GET route. The absence was real; the method was not. Read from the
    adapter's source, which sends `{guids: [...]}` in a body — "one POST rather than a GET per
    element", in its own words. A test that fetched this with GET would pass against a route the
    consumer can never reach, which is why the method is asserted explicitly below.
2.  The population was **9 endpoints, not 7**. `snapCandidates` (`GET /projects/{pid}/snap`) and
    `drawing` (`GET /projects/{pid}/drawings/{kind}.svg`) are called by the same adapter and appear
    nowhere in the report's table. Enumerated by listing every `transport.*` call in `kernel.ts`
    rather than by reading the summary — the report's table is a sample of a population nobody
    counted. Not fixed here (they are separate items); recorded so the next reader does not inherit
    "7" as the size of the gap.

**What each assertion is really guarding.**

*The tree comes from the file, not from names.* Every element already carries a `storey` STRING, and
grouping on it is a five-line function that produces a plausible tree with no GlobalIds in it —
against the repo's first non-negotiable, and wrong on the one model where a tree earns its keep: two
buildings that each have a "Level 2". The fixture below is exactly that model, so a name-grouped
implementation fails rather than merely being disapproved of.

*The refusal is not a null.* An index written before `index_schema: 2` has no tree, and so does a
model with no IfcProject. Those are the same absence and different answers — one is fixed by
re-publishing and the other is the truth — so the first is a 422 naming the remedy and the second is
a 404. Both are asserted, because a single code for both is what the version number exists to stop.

*An unknown guid is absent, not empty.* The adapter builds a Map and documents that a missing entry
means "not found" while a present-and-empty one means "no properties". Answering for everything
would collapse those, so the miss case is asserted directly.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_spatial_tree.py
"""
import os
import pathlib

os.environ["DATABASE_URL"] = "sqlite:///./test_spatial_tree.db"
os.environ["STORAGE_DIR"] = "./test_storage_spatial_tree"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_spatial_tree.db"):
    os.remove("./test_spatial_tree.db")

import ifcopenshell  # noqa: E402
import ifcopenshell.api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import model_index  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_data.properties_index import build_index, build_spatial_tree  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# ---------------------------------------------------------------------------------------------
# The fixture: ONE site, TWO buildings, and a same-named storey in each.
#
# Deliberately the model that separates a real tree from a name-grouped one. Grouping the elements
# by their `storey` string collapses these two storeys into a single node, and every assertion about
# counts below then fails — which is the whole reason the fixture is shaped this way rather than as
# the single-building model that would have passed either implementation.
# ---------------------------------------------------------------------------------------------
def _fixture() -> ifcopenshell.file:
    m = ifcopenshell.api.run("project.create_file")
    proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="Two Towers")
    ifcopenshell.api.run("unit.assign_unit", m,
                         units=[m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")])
    ifcopenshell.api.run("context.add_context", m, context_type="Model")
    site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="Riverside")
    ifcopenshell.api.run("aggregate.assign_object", m, products=[site], relating_object=proj)
    storeys = []
    for bname in ("Tower A", "Tower B"):
        b = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name=bname)
        ifcopenshell.api.run("aggregate.assign_object", m, products=[b], relating_object=site)
        for lvl, elev in (("Level 2", 4.0),):
            st = ifcopenshell.api.run("root.create_entity", m,
                                      ifc_class="IfcBuildingStorey", name=lvl)
            st.Elevation = elev
            ifcopenshell.api.run("aggregate.assign_object", m, products=[st], relating_object=b)
            storeys.append(st)
    # A space under one storey, to prove the chain reaches four levels deep rather than stopping at
    # the storey (which is where a hand-rolled three-level walk would stop and still look right).
    sp = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSpace", name="Lobby")
    ifcopenshell.api.run("aggregate.assign_object", m, products=[sp], relating_object=storeys[0])
    # One wall, contained in a storey rather than aggregated — it must NOT become a tree node.
    w = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcWall", name="W1")
    w.PredefinedType = "SOLIDWALL"
    ifcopenshell.api.run("spatial.assign_container", m,
                         products=[w], relating_structure=storeys[0])
    return m


MODEL = _fixture()
TREE = build_spatial_tree(MODEL)

# --- the tree itself -------------------------------------------------------------------------
check("a tree is built at all", TREE is not None)
check("the root is the IfcProject",
      TREE["ifcClass"] == "IfcProject" and TREE["name"] == "Two Towers", str(TREE and TREE["name"]))
site_nodes = TREE["children"]
check("the project aggregates one site", len(site_nodes) == 1, f"{len(site_nodes)} child(ren)")
bldgs = site_nodes[0]["children"]
check("the site aggregates BOTH buildings", len(bldgs) == 2,
      ", ".join(b["name"] for b in bldgs) or "none")
lvl2s = [st for b in bldgs for st in b["children"]]
check("both same-named storeys survive as SEPARATE nodes -- a name-grouped tree collapses these",
      len(lvl2s) == 2 and {s["name"] for s in lvl2s} == {"Level 2"},
      f"{len(lvl2s)} storey node(s)")
check("...and they carry DIFFERENT GlobalIds, which is what makes them addressable",
      len({s["guid"] for s in lvl2s}) == 2)
check("the chain reaches the IfcSpace under a storey (four levels, not three)",
      any(c["ifcClass"] == "IfcSpace" for st in lvl2s for c in st["children"]))
check("a storey carries its elevation", any(s.get("elevation") == 4.0 for s in lvl2s))


def _walk_nodes(node: dict):
    yield node
    for c in node["children"]:
        yield from _walk_nodes(c)


def _all_classes(node: dict) -> set[str]:
    out = {node["ifcClass"]}
    for c in node["children"]:
        out |= _all_classes(c)
    return out


check("a CONTAINED element is not a tree node -- containment is not decomposition",
      "IfcWall" not in _all_classes(TREE), ", ".join(sorted(_all_classes(TREE))))
check("every node carries a GlobalId", all(
    n for n in [TREE["guid"], *[c["guid"] for c in site_nodes]]))

# --- the twin: a file with no IfcProject is None, not an empty tree ---------------------------
_empty = ifcopenshell.api.run("project.create_file")
check("a file with no IfcProject yields None rather than a rootless tree",
      build_spatial_tree(_empty) is None)

# --- the index carries it, under a version ----------------------------------------------------
IDX = build_index(MODEL)
check("build_index stamps index_schema 2", IDX.get("index_schema") == 2, str(IDX.get("index_schema")))
check("...and embeds the tree", (IDX.get("spatial") or {}).get("ifcClass") == "IfcProject")
wall_rec = next((e for e in IDX["elements"] if e["ifc_class"] == "IfcWall"), None)
check("the element record now carries PredefinedType",
      (wall_rec or {}).get("predefined_type") == "SOLIDWALL", str((wall_rec or {}).get("predefined_type")))

# ---------------------------------------------------------------------------------------------
# The routes.
# ---------------------------------------------------------------------------------------------
with TestClient(app) as cl:
    pid = cl.post("/projects", json={"name": "conf"}).json()["id"]

    # --- v1 index: REFUSED with a remedy, not answered with a null ---
    v1 = {k: v for k, v in IDX.items() if k not in ("spatial", "index_schema")}
    model_index.load(pid, v1)
    r = cl.get(f"/projects/{pid}/spatial-tree")
    check("a pre-v2 index is REFUSED (422), not answered with null", r.status_code == 422,
          f"{r.status_code} {r.text[:120]}")
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    check("...the refusal declares `refused`, which the consumer's adapter reads before the status",
          body.get("code") == "refused", str(body.get("code")))
    check("...and names the remedy rather than only the problem",
          "re-upload" in (body.get("detail") or "").lower()
          or "re-run" in (body.get("detail") or "").lower(), (body.get("detail") or "")[:80])

    # --- v2 index: the real tree, in the consumer's shape ---
    model_index.load(pid, IDX)
    r = cl.get(f"/projects/{pid}/spatial-tree")
    check("a v2 index answers 200", r.status_code == 200, str(r.status_code))
    root = r.json()
    check("the payload is ONE root node, not a list", isinstance(root, dict))
    check("every node is a {ref:{modelId,guid}, ifcClass, name, children} -- the documented shape",
          set(root) >= {"ref", "ifcClass", "name", "children"}
          and set(root["ref"]) == {"modelId", "guid"}, str(sorted(root)))
    check("ref.modelId is the IfcProject GlobalId, not the project id",
          root["ref"]["modelId"] == MODEL.by_type("IfcProject")[0].GlobalId
          and root["ref"]["modelId"] != pid, root["ref"]["modelId"])
    served_l2 = [st for s in root["children"] for b in s["children"] for st in b["children"]]
    check("both storeys survive the route too", len(served_l2) == 2, f"{len(served_l2)}")
    check("a storey's elevation ships with the unit it is IN",
          any("elevationUnit" in s for s in served_l2))

    # --- a model with no spatial structure is a 404, and that is a DIFFERENT answer ---
    pid2 = cl.post("/projects", json={"name": "flat"}).json()["id"]
    model_index.load(pid2, {**IDX, "spatial": None})
    r = cl.get(f"/projects/{pid2}/spatial-tree")
    check("a v2 index with no IfcProject is 404 -- distinct from the 422 above",
          r.status_code == 404, str(r.status_code))

    # --- POST /elements/properties ---
    guids = [e["guid"] for e in IDX["elements"]]
    check("the fixture has at least one element to ask about", bool(guids), f"{len(guids)}")
    r = cl.post(f"/projects/{pid}/elements/properties", json={"guids": guids})
    check("bulk properties answers 200 to a POST", r.status_code == 200, str(r.status_code))
    rows = r.json()
    check("...returning a LIST, one entry per hit", isinstance(rows, list) and len(rows) == len(guids),
          f"{len(rows)} row(s) for {len(guids)} guid(s)")
    check("...each entry keyed camelCase per the contract",
          all(set(x) >= {"guid", "ifcClass", "psets"} for x in rows), str(sorted(rows[0])))
    check("...carrying predefinedType where IFC states one",
          any(x.get("predefinedType") == "SOLIDWALL" for x in rows))

    # The assertion the contract turns on.
    r = cl.post(f"/projects/{pid}/elements/properties",
                json={"guids": [guids[0], "0uNkN0wNgU1dN0tHeRe1"]})
    rows = r.json()
    check("an unknown guid is ABSENT from the response, not present-and-empty",
          len(rows) == 1 and rows[0]["guid"] == guids[0], f"{len(rows)} row(s)")
    check("...so an all-unknown request is an empty list, not a 404",
          cl.post(f"/projects/{pid}/elements/properties",
                  json={"guids": ["0uNkN0wNgU1dN0tHeRe1"]}).json() == [])

    # A repeated guid must not yield two rows: the caller builds a Map, where the second silently wins.
    r = cl.post(f"/projects/{pid}/elements/properties", json={"guids": [guids[0], guids[0]]})
    check("a repeated guid yields ONE row", len(r.json()) == 1, f"{len(r.json())}")

    # Refused, not truncated.
    r = cl.post(f"/projects/{pid}/elements/properties", json={"guids": ["x"] * 5001})
    check("an over-long list is REFUSED (400), never silently truncated", r.status_code == 400,
          f"{r.status_code} {r.text[:80]}")
    check("a malformed body is refused",
          cl.post(f"/projects/{pid}/elements/properties", json={"guids": "abc"}).status_code == 400)

    # --- the method matters: the report probed this with GET and mis-diagnosed the result ---
    r = cl.get(f"/projects/{pid}/elements/properties")
    check("GET on the same path still resolves to /elements/{guid} -- which is how the run was "
          "misread, and why the POST is the assertion", r.status_code == 404, str(r.status_code))

# ---------------------------------------------------------------------------------------------
# The same thing on a REAL file, because the fixture above has one element.
#
# A one-element fixture can show that the join compiles. It cannot show that the join HOLDS, and the
# two questions look identical from a green run — this repo's "a fixture too small manufactures
# numbers" lesson. `school_str.ifc` is 8.6 MB with 1,551 elements over five storeys, and the two
# things it settles are the two the synthetic model was structurally unable to raise:
#
#   1. **Every element resolves to a node of the tree.** Not "has a storey_guid" — has one that is
#      actually IN the tree. Those come from different code paths (`storey_of` walks containment and
#      aggregation; the tree walks decomposition) and nothing but a real file with real relationships
#      makes them agree or disagree.
#   2. **Elevations are MILLIMETRES here.** The consumer's interface documents `elevation` as "metres
#      above project zero" and this file returns 3800 / 7600 / 11400. Converting on the assumption of
#      metres would put a four-storey school's roof 11.4 KILOMETRES up, from numbers that look
#      entirely sensible in the payload. That is why the value passes through unconverted with its
#      unit stated — and it is asserted here rather than left as a comment, because the tempting
#      "fix" is a one-line divide by 1000 that no other test in this file would notice.
# ---------------------------------------------------------------------------------------------
_SAMPLE = pathlib.Path(__file__).resolve().parents[2] / "samples" / "school_str.ifc"
if not _SAMPLE.exists():
    print("SKIP  real-model checks — sample missing:", _SAMPLE)
else:
    real = ifcopenshell.open(str(_SAMPLE))
    rtree = build_spatial_tree(real)
    ridx = build_index(real)

    def _guids(n: dict) -> set:
        out = {n["guid"]}
        for c in n["children"]:
            out |= _guids(c)
        return out

    in_tree = _guids(rtree)
    rel = ridx["elements"]
    placed = [e for e in rel if e.get("storey_guid")]
    resolved = [e for e in placed if e["storey_guid"] in in_tree]
    check("the real model indexes a meaningful number of elements", len(rel) > 500, str(len(rel)))
    check("every element carries a storey_guid", len(placed) == len(rel),
          f"{len(placed)}/{len(rel)}")
    check("...and every one of them RESOLVES to a node of the tree -- containment and decomposition "
          "are different walks, and only a real file can make them agree",
          len(resolved) == len(placed), f"{len(resolved)}/{len(placed)}")
    storeys = [n for n in _walk_nodes(rtree) if n["ifcClass"] == "IfcBuildingStorey"]
    check("the real model has more than one storey", len(storeys) > 1, str(len(storeys)))
    elevs = [n["elevation"] for n in storeys if "elevation" in n]
    check("storey elevations are passed through UNCONVERTED -- this file is in millimetres, and a "
          "divide-by-1000 'fix' would put the roof 11.4 km up",
          any(abs(e) > 100 for e in elevs), ", ".join(f"{e:.1f}" for e in elevs))


if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print(f"test_spatial_tree OK  ({len(TREE['children'][0]['children'])} buildings, "
      f"{len(IDX['elements'])} elements)")
