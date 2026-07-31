"""R22-PROVENANCE ② over HTTP — citations survive the round trip, which is the whole point.

The rules are pinned in `test_assumption_provenance.py`. What only a live app shows is the thing that
made this item a build rather than a seam: a `sources` block POSTed to `/proforma/scenarios` used to
be accepted with a **200** and then discarded by `model_dump()` before storage, because pydantic v2
defaults to `extra="ignore"`. The caller had no signal at all — no 4xx, no warning, no missing field
in the response they were likely to read.

So the load-bearing assertion here is not that provenance is computed. It is that what you POST is
what comes back out of the database.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_assumption_provenance_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_assumption_provenance_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_assumption_provenance_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_assumption_provenance_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# Fixture shape copied from test_fin_gov.py rather than invented.
DEAL = {
    "timing": {"construction_months": 6, "leaseup_months": 3, "hold_years": 2,
               "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 1_000_000, "curve": "upfront",
         "start_month": 0, "end_month": 0},
        {"category": "hard", "name": "Build", "amount": 4_000_000, "curve": "scurve",
         "start_month": 1, "end_month": 5},
    ],
    "debt": {"ltc": 0.6, "rate": 0.08, "points": 0.01, "funding": "equity_first"},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 700_000, "other_income_annual": 0,
                   "opex_annual": 250_000, "stabilized_occ": 0.95, "credit_loss_pct": 0.02},
    "exit": {"exit_cap": 0.06, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]},
}
SOURCES = {
    "exit.exit_cap": [{"source_type": "doc", "document_id": "appraisal.pdf",
                       "page": 12, "revision": "B"}],
    "operations.potential_rent_annual": [{"source_type": "doc", "document_id": "rent_roll.pdf",
                                          "page": 3, "revision": "B"}],
}

with TestClient(app) as c:
    c.headers.update({"X-User": "prov@test"})
    pid = c.post("/projects", json={"name": "Provenance"}).json()["id"]

    # --- an UNSOURCED scenario reports its gaps by name -------------------------------------------
    bare = c.post("/proforma/scenarios",
                  json={"name": "Unsourced", "project_id": pid, "assumptions": DEAL})
    check("a scenario can be created", bare.status_code in (200, 201), bare.text[:200])
    bid = bare.json()["id"]

    b = c.get(f"/proforma/scenarios/{bid}/provenance")
    check("GET /provenance answers 200", b.status_code == 200, b.text[:200])
    B = b.json()
    check("  an unsourced deal reads 0% coverage", B["coverage_pct"] == 0.0, B["coverage_pct"])
    check("  every material assumption is NAMED as uncited, not just counted",
          len(B["uncited"]) == B["material_count"] and B["material_count"] > 5,
          (len(B["uncited"]), B["material_count"]))
    check("  the exit cap is one of them — a driver, not a switch",
          "exit.exit_cap" in B["uncited"], B["uncited"][:6])
    check("  and the scenario is named so the figure is traceable",
          B["scenario_name"] == "Unsourced", B["scenario_name"])

    # --- THE REGRESSION: sources survive POST -> storage -> GET -----------------------------------
    srcd = c.post("/proforma/scenarios",
                  json={"name": "Sourced", "project_id": pid,
                        "assumptions": {**DEAL, "sources": SOURCES}})
    check("a scenario with sources is accepted", srcd.status_code in (200, 201), srcd.text[:200])
    sid = srcd.json()["id"]

    stored = c.get(f"/proforma/scenarios/{sid}").json()
    check("`sources` SURVIVES the round trip — it used to be silently dropped",
          (stored.get("assumptions") or {}).get("sources") is not None,
          sorted((stored.get("assumptions") or {}).keys()))
    check("  with the page and revision intact, not just the key",
          stored["assumptions"]["sources"]["exit.exit_cap"][0]["page"] == 12
          and stored["assumptions"]["sources"]["exit.exit_cap"][0]["revision"] == "B",
          stored["assumptions"]["sources"]["exit.exit_cap"])

    S = c.get(f"/proforma/scenarios/{sid}/provenance").json()
    check("the two cited drivers are counted", S["cited_count"] == 2, S["cited_count"])
    check("  coverage rises above zero but not to 100 — the rest are still uncited",
          0 < S["coverage_pct"] < 100, S["coverage_pct"])
    check("  and the remaining gaps are still named",
          "debt.ltc" in S["uncited"], S["uncited"][:6])
    check("  the solve still works on a scenario carrying sources",
          isinstance((srcd.json().get("result") or {}).get("returns", {}).get("equity_irr"),
                     (int, float)),
          (srcd.json().get("result") or {}).get("returns"))

    # --- stale revisions are visible over the wire ------------------------------------------------
    T = c.get(f"/proforma/scenarios/{sid}/provenance?revision=C").json()
    check("citations against an older revision are reported stale",
          T["stale_citation_count"] == 2, T["stale_citation_count"])
    check("  they still count as cited — stale is not absent",
          T["cited_count"] == 2, T["cited_count"])

    # --- a citation aimed at nothing cannot inflate the number ------------------------------------
    bogus = c.post("/proforma/scenarios",
                   json={"name": "Bogus", "project_id": pid,
                         "assumptions": {**DEAL, "sources": {"operations.rent": SOURCES[
                             "exit.exit_cap"]}}}).json()["id"]
    G = c.get(f"/proforma/scenarios/{bogus}/provenance").json()
    check("a source against a non-existent path does not count as coverage",
          G["cited_count"] == 0 and G["coverage_pct"] == 0.0,
          (G["cited_count"], G["coverage_pct"]))
    check("  and it is reported as orphaned rather than ignored",
          G["orphaned_sources"] == ["operations.rent"], G["orphaned_sources"])

    check("an unknown scenario is 404, not an empty provenance report",
          c.get("/proforma/scenarios/nope/provenance").status_code == 404)

    # additive — the existing proforma surface is untouched
    check("the existing scenario list still works",
          c.get("/proforma/scenarios").status_code == 200)

print()
if FAILED:
    print(f"assumption_provenance_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("assumption_provenance_route: all checks passed")
