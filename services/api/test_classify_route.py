"""R22-CLASSIFY-AI over HTTP — against a real IFC, including one classified through the edit recipe.

The engine is tested in `test_classify_assist.py` against dicts. What only a live app can show is
the round trip that matters: propose a code, apply it through the ordinary `set_classification` edit
recipe, re-read the model, and confirm the element now reads as **declared** — i.e. that what this
module proposes and what the platform writes are the same thing, read back by a path that did not
write them.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_classify_route.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_classify_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_classify_route"
os.environ["IFC_DIR"] = "./test_ifc_classify_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_classify_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

import ifcopenshell  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_data import edit_struct, massing  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# A model shaped like an import: named walls that a keyword can read, and a proxy that nothing maps.
tmp = Path(tempfile.gettempdir()) / "classify_route.ifc"
massing.generate_blank_ifc(str(tmp), name="Classify Tower", storeys=1, storey_height=3.5)
m = ifcopenshell.open(str(tmp))
cmu = edit_struct.add_wall(m, (0.0, 0.0), (6.0, 0.0), height=3.0, storey="Level 1")
m.by_guid(cmu).Name = "CMU Partition Type A"
plain = edit_struct.add_wall(m, (0.0, 0.0), (0.0, 4.0), height=3.0, storey="Level 1")
m.by_guid(plain).Name = "Wall-02"
proxy = m.create_entity("IfcBuildingElementProxy", GlobalId=ifcopenshell.guid.new(), Name="Widget 12")
m.write(str(tmp))

with TestClient(app) as c:
    c.headers.update({"X-User": "classify@test"})
    pid = c.post("/projects", json={"name": "Classify Tower"}).json()["id"]

    pre = c.get(f"/projects/{pid}/classify/coverage")
    check("no source IFC → a 4xx, not a 500", 400 <= pre.status_code < 500, pre.status_code)

    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("model.ifc", tmp.read_bytes(), "application/octet-stream")})
    check("the model uploads", up.status_code == 200, up.text[:160])

    cov = c.get(f"/projects/{pid}/classify/coverage")
    check("GET /classify/coverage answers 200", cov.status_code == 200, cov.text[:200])
    C = cov.json()
    check("  an unclassified import reads as 0% classified", C["classified_pct"] == 0.0, C)
    check("  which is the honest starting point, not the implicit 100% of a default bucket",
          C["declared"] == 0 and C["total"] >= 3, C["total"])
    check("  the proxy is counted as unmapped", C["unmapped"] >= 1, C["by_basis"])
    check("  with a warning naming the estimate consequence",
          "default bucket" in (C["unmapped_warning"] or ""))
    check("  and the coverage response does not carry the full row set",
          "rows" not in C, sorted(C))

    props = c.get(f"/projects/{pid}/classify/proposals")
    check("GET /classify/proposals answers 200", props.status_code == 200, props.text[:200])
    P = props.json()
    rows = {r["guid"]: r for r in P["rows"]}
    check("  the CMU-named wall proposes unit masonry on its own name",
          rows[cmu]["basis"] == "keyword" and rows[cmu]["code"] == "04 20 00", rows.get(cmu))
    check("  the plainly-named wall falls to the class map at low confidence",
          rows[plain]["basis"] == "class_map" and rows[plain]["confidence"] == "low",
          rows.get(plain))
    check("  the proxy gets no code at all",
          rows[proxy.GlobalId]["basis"] == "unmapped" and rows[proxy.GlobalId]["code"] is None)

    only = c.get(f"/projects/{pid}/classify/proposals?basis=unmapped").json()
    check("filtering by basis works", {r["basis"] for r in only["rows"]} == {"unmapped"})
    check("an unknown basis is a 422",
          c.get(f"/projects/{pid}/classify/proposals?basis=vibes").status_code == 422)
    check("an unknown system is a 422",
          c.get(f"/projects/{pid}/classify/coverage?system=nonsense").status_code == 422)
    uni = c.get(f"/projects/{pid}/classify/coverage?system=uniclass")
    check("uniclass is refused with its standing reason", uni.status_code == 422
          and "never guessed" in uni.text, uni.text[:120])

    # Truncation must announce itself — a page that stops at the limit and says nothing reads as the
    # whole set, and the whole set is precisely what a coverage exercise needs.
    one = c.get(f"/projects/{pid}/classify/proposals?limit=1").json()
    check("a truncated page says how many rows it did not show",
          one["truncated"] is True and "further row" in one["truncation_note"], one.get("truncation_note"))

    # --- the round trip -----------------------------------------------------------------------------
    plan = c.post(f"/projects/{pid}/classify/plan",
                  json={"accept": [cmu, plain, proxy.GlobalId], "system": "masterformat"})
    check("POST /classify/plan answers 200", plan.status_code == 200, plan.text[:200])
    PL = plan.json()
    check("  the two classifiable walls become steps", PL["count"] == 2, PL["count"])
    check("  and the proxy is skipped with a reason",
          [s["guid"] for s in PL["skipped"]] == [proxy.GlobalId], PL["skipped"])
    check("  the steps are ordinary set_classification recipes",
          {s["recipe"] for s in PL["steps"]} == {"set_classification"})
    check("an empty accept list is a 422",
          c.post(f"/projects/{pid}/classify/plan", json={"accept": []}).status_code == 422)

    applied = c.post(f"/projects/{pid}/edit/batch", json={"steps": PL["steps"], "publish": False})
    check("the plan applies through the ordinary authoring path", applied.status_code == 200,
          applied.text[:250])

    # Re-read through read_declared — a path that did not write these — and confirm they now count.
    after = c.get(f"/projects/{pid}/classify/coverage").json()
    check("the applied codes now read back as DECLARED", after["declared"] == 2, after["by_basis"])
    check("  so coverage rose, and only because the MODEL now says so",
          after["classified_pct"] > C["classified_pct"], (C["classified_pct"], after["classified_pct"]))
    rows2 = {r["guid"]: r for r in c.get(f"/projects/{pid}/classify/proposals").json()["rows"]}
    check("  the CMU wall reads as declared with the code we proposed",
          rows2[cmu]["basis"] == "declared" and rows2[cmu]["code"] == "04 20 00", rows2.get(cmu))
    check("  the proxy is still unmapped — nothing was invented for it",
          rows2[proxy.GlobalId]["basis"] == "unmapped")

    replan = c.post(f"/projects/{pid}/classify/plan",
                    json={"accept": [cmu], "system": "masterformat"}).json()
    check("re-accepting an already-declared element is refused, not double-tagged",
          replan["count"] == 0 and "already declared" in replan["skipped"][0]["reason"],
          replan["skipped"])

print()
if FAILED:
    print(f"classify_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("classify_route: all checks passed")
