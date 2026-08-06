"""R22-OPTION-OBJECT over HTTP — the joined record, against the engines it claims to agree with.

`test_option_object.py` pins the join's rules against a hand-built payload. That is not enough here,
and this file exists because of how it was not enough: the first `join()` read `total_cost`,
`equity_irr` and `carbon_intensity_kgco2e_m2`, **none of which any engine emits**. Against a real
project it reported all five axes absent for every option, and all nineteen unit checks passed —
because the fixture was invented alongside the code, so both sides of the join were wrong in the same
way and agreed perfectly.

A join is defined by the field names on both sides of it. A test that supplies both sides therefore
cannot see the only defect that matters. This one supplies neither: it POSTs design options through
the module engine and reads the record back over HTTP, so the names have to line up for real.

The load-bearing check is the last group — every axis on the record is compared against the SAME
number served by the route that owns it. That is the "re-derives nothing" claim stated as an
assertion, and it is what stops this record and the three screens beside it from ever disagreeing.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_option_object_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_option_object_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_option_object_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_option_object_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


with TestClient(app) as c:
    c.headers.update({"X-User": "optobj@test"})
    pid = c.post("/projects", json={"name": "Option Object"}).json()["id"]

    def opt(**data):
        r = c.post(f"/projects/{pid}/modules/design_option", json={"data": data})
        assert r.status_code in (200, 201), (r.status_code, r.text[:200])
        return r.json()

    empty = c.get(f"/projects/{pid}/design/options/record")
    check("GET /design/options/record answers 200 with nothing set up", empty.status_code == 200,
          empty.text[:200])
    check("  an empty project is an empty record, not an error",
          empty.json()["option_count"] == 0 and empty.json()["comparable_count"] == 0,
          empty.json())

    # A — carbon DECLARED, cost and return typed on the option. All five axes.
    opt(name="A — measured", gross_area_sf=120_000, unit_count=140, building_type="multifamily",
        embodied_kgco2e=4_684_000, hard_cost=48_000_000, irr_pct=18.1)
    # B — no carbon figure, but a recognised building type, so carbon comes from the BENCHMARK path.
    opt(name="B — benchmarked", gross_area_sf=96_000, unit_count=110, building_type="multifamily",
        hard_cost=39_000_000, irr_pct=16.4)
    # C — geometry and cost only. No carbon basis at all, no return. This is the option the ring is
    # about: it must not come back looking complete, and must not come back as zeroes.
    opt(name="C — unmeasured", gross_area_sf=80_000, unit_count=90, hard_cost=33_000_000)

    r = c.get(f"/projects/{pid}/design/options/record")
    check("the joined record answers 200", r.status_code == 200, r.text[:200])
    J = r.json()
    row = {o["name"]: o for o in J["options"]}

    check("all three options appear", J["option_count"] == 3, J["option_count"])
    check("THE KEY NAMES LINE UP — a fully-populated option has every axis present",
          row["A — measured"]["comparable"] is True, row["A — measured"])
    check("  with real numbers on all five, not Nones",
          all(isinstance(v, (int, float)) for v in row["A — measured"]["axes"].values()),
          row["A — measured"]["axes"])
    check("  geometry and unit mix came from the option card",
          row["A — measured"]["axes"]["geometry"] == 120_000
          and row["A — measured"]["axes"]["unit_mix"] == 140, row["A — measured"]["axes"])
    check("  cost came through as the hard cost, not None",
          row["A — measured"]["axes"]["cost"] == 48_000_000, row["A — measured"]["axes"]["cost"])
    check("  and the return is the recorded IRR percentage",
          row["A — measured"]["axes"]["returns"] == 18.1, row["A — measured"]["axes"]["returns"])

    check("the benchmarked option is comparable too — a benchmark IS a basis",
          row["B — benchmarked"]["comparable"] is True, row["B — benchmarked"])
    check("  but the record says the carbon was benchmarked, not measured",
          (row["A — measured"]["carbon_basis"], row["B — benchmarked"]["carbon_basis"])
          == ("declared", "benchmark"),
          (row["A — measured"]["carbon_basis"], row["B — benchmarked"]["carbon_basis"]))

    cc = row["C — unmeasured"]
    check("THE REFUSAL — the unmeasured option is NOT comparable", cc["comparable"] is False, cc)
    check("  carbon and returns are ABSENT, not 0.0",
          cc["axes"]["carbon"] is None and cc["axes"]["returns"] is None, cc["axes"])
    check("  named as missing", sorted(cc["missing_axes"]) == ["carbon", "returns"],
          cc["missing_axes"])
    check("  while the axes it does have survive — absence is per-axis",
          cc["axes"]["geometry"] == 80_000 and cc["axes"]["cost"] == 33_000_000, cc["axes"])
    check("comparable_count is the number the ring is about", J["comparable_count"] == 2,
          J["comparable_count"])
    check("  and the incomparable option is named for the reader",
          [x["name"] for x in J["incomparable"]] == ["C — unmeasured"], J["incomparable"])
    check("the record still does not rank",
          not any(k in J for k in ("rank", "ranked", "score", "recommended", "best")), sorted(J))

    # --- THE CLAIM: re-derives nothing. Every axis equals what its owning route serves. ------------
    comp = c.get(f"/projects/{pid}/design/options/compare").json()
    carb = c.get(f"/projects/{pid}/design/options/carbon").json()
    econ = c.get(f"/projects/{pid}/design/options/economics").json()
    g = {o["name"]: o for o in comp["options"]}
    k = {o["name"]: o for o in carb["options"]}
    e = {o["name"]: o for o in econ["options"]}

    for nm in ("A — measured", "B — benchmarked", "C — unmeasured"):
        ax = row[nm]["axes"]
        check(f"{nm}: geometry equals /compare's gross_area_sf", ax["geometry"] == g[nm]["gross_area_sf"],
              (ax["geometry"], g[nm]["gross_area_sf"]))
        check(f"{nm}: unit mix equals /compare's unit_count", ax["unit_mix"] == g[nm]["unit_count"],
              (ax["unit_mix"], g[nm]["unit_count"]))
        check(f"{nm}: carbon equals /carbon's kgco2e_per_m2",
              ax["carbon"] == k[nm]["kgco2e_per_m2"], (ax["carbon"], k[nm]["kgco2e_per_m2"]))
        check(f"{nm}: returns equal /economics' irr_pct", ax["returns"] == e[nm]["irr_pct"],
              (ax["returns"], e[nm]["irr_pct"]))
        check(f"{nm}: cost equals /economics' hard_cost", ax["cost"] == e[nm]["hard_cost"],
              (ax["cost"], e[nm]["hard_cost"]))

print()
if FAILED:
    print(f"option_object_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("option_object_route: all checks passed")
