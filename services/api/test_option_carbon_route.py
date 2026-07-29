"""R22-CARBON-OPTION over HTTP — the figure reaches the option CARD, which is the whole ask.

The arithmetic is pinned in `test_option_carbon.py`. What only a live app shows is that the two new
schema fields actually round-trip through the module engine (a field the schema does not accept is
silently dropped, and the roll-up then reports `unavailable` for data the user did enter), and that
carbon appears on `/design/options/compare` — the existing card — rather than only on a new endpoint
nobody opens.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_option_carbon_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_option_carbon_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_option_carbon_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_option_carbon_route.db",):
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
    c.headers.update({"X-User": "carbon@test"})
    pid = c.post("/projects", json={"name": "Carbon Options"}).json()["id"]

    def opt(**data):
        r = c.post(f"/projects/{pid}/modules/design_option", json={"data": data})
        assert r.status_code in (200, 201), (r.status_code, r.text[:200])
        return r.json()

    empty = c.get(f"/projects/{pid}/design/options/carbon")
    check("GET /design/options/carbon answers 200 with no options", empty.status_code == 200,
          empty.text[:200])
    check("  and reports nothing measurable rather than an empty success",
          empty.json()["measured_count"] == 0 and empty.json()["message"] is not None)

    # The schema fields must actually persist. If `building_type` were rejected by the module schema
    # the roll-up would report `unavailable` and look like a data-entry problem rather than a bug.
    a = opt(name="A — Office", gross_area_sf=50_000, building_type="office", hard_cost=20_000_000)
    check("the new building_type field round-trips through the module engine",
          (a.get("data") or {}).get("building_type") == "office", a.get("data"))
    b = opt(name="B — Warehouse", gross_area_sf=50_000, building_type="warehouse",
            hard_cost=12_000_000)
    # Deliberately small and carbon-DENSE: 900 tCO2e over 20,000 sf is ~484 kgCO2e/m2, so D wins on
    # total while losing on intensity. Lowest-total and lowest-intensity must be able to disagree, or
    # the roll-up is reporting one number twice and a small scheme always looks green.
    d = opt(name="D — Measured", gross_area_sf=20_000, building_type="office",
            embodied_kgco2e=900_000, hard_cost=21_000_000)
    check("  as does embodied_kgco2e",
          (d.get("data") or {}).get("embodied_kgco2e") in (900_000, 900_000.0),
          (d.get("data") or {}).get("embodied_kgco2e"))
    opt(name="C — Unknowable", hard_cost=15_000_000)          # no area, no type

    r = c.get(f"/projects/{pid}/design/options/carbon")
    check("the roll-up answers 200", r.status_code == 200, r.text[:200])
    J = r.json()
    check("  four options, three measurable",
          (J["count"], J["measured_count"], J["unavailable_count"]) == (4, 3, 1),
          (J["count"], J["measured_count"], J["unavailable_count"]))
    check("  the declared option is lowest by total", J["lowest_total"] == "D — Measured",
          J["lowest_total"])
    check("  the warehouse is lowest by intensity", J["lowest_intensity"] == "B — Warehouse",
          J["lowest_intensity"])
    check("  the mixed basis is declared, not left for the reader to infer", J["mixed_basis"] is True)
    unk = next(o for o in J["options"] if o["name"] == "C — Unknowable")
    check("  the unmeasurable option carries None, not 0", unk["embodied_kgco2e"] is None,
          unk["embodied_kgco2e"])
    check("  and says what to record", "no gross area" in (unk["note"] or ""), unk["note"])

    # THE ASK: carbon on the existing card, beside cost and area.
    comp = c.get(f"/projects/{pid}/design/options/compare")
    check("the existing option card still answers 200", comp.status_code == 200, comp.text[:200])
    C = comp.json()
    card = {o["name"]: o for o in C["options"]}
    check("  every option on the card carries an embodied-carbon field",
          all("embodied_kgco2e" in o for o in C["options"]))
    check("  and its basis, so a declared figure is distinguishable from a benchmarked one",
          card["D — Measured"]["carbon_basis"] == "declared"
          and card["A — Office"]["carbon_basis"] == "benchmark",
          [(o["name"], o["carbon_basis"]) for o in C["options"]])
    check("  carbon is a named best-in-class metric on the card",
          "kgco2e_per_sf" in C["leaders"], sorted(C["leaders"]))
    check("  the leader is the warehouse, by INTENSITY not by total",
          C["leaders"]["kgco2e_per_sf"]["option"] == "B — Warehouse",
          C["leaders"]["kgco2e_per_sf"])
    check("  the unmeasurable option is never named best-in-class on any metric",
          "C — Unknowable" not in [v["option"] for v in C["leaders"].values()],
          {k: v["option"] for k, v in C["leaders"].items()})
    # Embodied and operational are different lifecycle stages; conflating them is the failure the
    # separate fields exist to prevent.
    check("  embodied carbon has not been merged into the operational energy_eui field",
          card["A — Office"]["energy_eui"] is None
          and card["A — Office"]["embodied_kgco2e"] is not None)

    # Additive: nothing that worked before may have changed shape.
    check("the pre-existing card metrics are untouched",
          all(k in card["A — Office"] for k in
              ("cost_per_sf", "irr_pct", "gross_area_sf", "efficiency_pct", "unit_count")))
    check("  and the existing project-level carbon endpoint still works",
          c.get(f"/projects/{pid}/carbon").status_code == 200)

print()
if FAILED:
    print(f"option_carbon_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("option_carbon_route: all checks passed")
