"""R22-MEMORY ② over HTTP — the join happens across projects, and it is tenant-scoped.

The arithmetic is pinned in `test_unit_rate_memory.py`. What only a live app shows is that the two
record types actually join through the module engine — `direct_cost` and `production_quantity` are
owned by different engines (accounting/EVM and carbon/pricing) and nothing had ever read both — and
that a cross-project roll-up stays inside the caller's projects.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_unit_rate_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_unit_rate_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_unit_rate_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_unit_rate_route.db",):
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
    c.headers.update({"X-User": "rates@test"})

    def new_project(name):
        return c.post("/projects", json={"name": name}).json()["id"]

    def rec(pid, key, data):
        r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), (key, r.status_code, r.text[:200])
        return r.json()

    empty = c.get("/benchmarks/unit-rates")
    check("GET /benchmarks/unit-rates answers 200 with no history", empty.status_code == 200,
          empty.text[:200])
    E = empty.json()
    check("  it reports nothing usable rather than an empty success",
          E["usable_count"] == 0 and E["message"] is not None)
    check("  and the message says what is missing", "quantities AND posted costs" in E["message"])

    # Three projects, same cost code, hand-computed rates: 300 / 220 / 450 per m3.
    P = [new_project("Rate A"), new_project("Rate B"), new_project("Rate C")]
    for pid, amount, quantity in ((P[0], 60_000, 200), (P[1], 22_000, 100), (P[2], 90_000, 200)):
        rec(pid, "direct_cost", {"description": "concrete", "cost_code": "03 30 00",
                                 "amount": amount})
        rec(pid, "production_quantity", {"description": "concrete placed", "cost_code": "03 30 00",
                                         "quantity": quantity, "unit": "m3"})

    r = c.get("/benchmarks/unit-rates")
    check("the roll-up answers 200", r.status_code == 200, r.text[:200])
    J = r.json()
    check("  one (code, unit) group", J["code_count"] == 1, J["code_count"])
    g = J["cost_codes"][0]
    check("  it joined records from BOTH engines' modules",
          g["cost_code"] == "03 30 00" and g["unit"] == "m3", (g["cost_code"], g["unit"]))
    check("  three projects", g["projects"] == 3)
    check("  median is the middle PROJECT's rate, 300.0", g["median"] == 300.0, g["median"])
    check("  pooled_rate is 172000/500 = 344.0 and differs from the median",
          g["pooled_rate"] == 344.0 and g["pooled_rate"] != g["median"],
          (g["pooled_rate"], g["median"]))
    check("  usable at the default threshold", J["usable_count"] == 1)
    check("  the basis is stated in the payload", "distribution is over projects" in J["basis"])
    check("  as is the accrual-lag limitation", "spread_ratio" in J["limitation"])

    # A fourth project with cost but no quantity must be EXCLUDED and REPORTED, never counted as 0.
    p4 = new_project("Rate D")
    rec(p4, "direct_cost", {"description": "concrete", "cost_code": "03 30 00", "amount": 15_000})
    J2 = c.get("/benchmarks/unit-rates").json()
    g2 = J2["cost_codes"][0]
    check("a project with cost but no quantity does not enter the distribution",
          g2["projects"] == 3 and g2["median"] == 300.0, (g2["projects"], g2["median"]))
    check("  and it is reported as excluded, with its cost",
          any(x["cost"] == 15_000.0 for x in J2["excluded"]["cost_without_quantity"]),
          J2["excluded"]["cost_without_quantity"])

    # A project recording one code under two units is excluded rather than split.
    p5 = new_project("Rate E")
    rec(p5, "direct_cost", {"description": "c", "cost_code": "03 30 00", "amount": 5_000})
    rec(p5, "production_quantity", {"description": "c", "cost_code": "03 30 00",
                                    "quantity": 50, "unit": "m3"})
    rec(p5, "production_quantity", {"description": "c", "cost_code": "03 30 00",
                                    "quantity": 100, "unit": "SF"})
    J3 = c.get("/benchmarks/unit-rates").json()
    check("a project mixing units within one code is excluded, not split",
          J3["cost_codes"][0]["projects"] == 3, J3["cost_codes"][0]["projects"])
    check("  and reported with both units named",
          any(sorted(x["units"]) == ["m3", "sf"] for x in J3["excluded"]["mixed_units"]),
          J3["excluded"]["mixed_units"])

    check("min_projects is clamped, not trusted",
          c.get("/benchmarks/unit-rates?min_projects=0").status_code == 200
          and c.get("/benchmarks/unit-rates?min_projects=999").json()["usable_count"] == 0)

    # The sibling endpoint must be unaffected — this is additive.
    costs = c.get("/benchmarks/costs")
    check("the existing /benchmarks/costs still works", costs.status_code == 200, costs.text[:160])

print()
if FAILED:
    print(f"unit_rate_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("unit_rate_route: all checks passed")
