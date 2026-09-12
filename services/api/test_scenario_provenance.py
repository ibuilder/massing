"""SCENARIO-SOURCES — the two ways a provenance figure can read better than the deal is.

`GET /proforma/scenarios/{sid}/provenance` (R22-PROVENANCE ②) reports which of a scenario's MATERIAL
assumptions carry a document citation. It had no client caller until SCENARIO-SOURCES: its leaf
`provenance` was read as reachable by the route gate because `ProformaResult.provenance` is a FIELD of
that name on a different reply.

The engine is sound. What this file pins are the two properties a SCREEN over it has to respect,
because both are ways for a true number to be read as a stronger claim than it is:

  1. **COVERAGE AND CURRENCY ARE DIFFERENT AXES.** `STATUS_CITED` is assigned whenever any readable
     citation exists, regardless of the revision it names. So `coverage_pct` can read **100.0 while
     every citation points at a superseded document**. A memo quoting the percentage alone says
     "fully sourced" about evidence nobody has re-checked.

  2. **`stale_citation_count: 0` IS AMBIGUOUS.** Staleness is computed only when the caller supplies
     `?revision=` -- `[c for c in cites if current_revision and ...]` -- so with no revision the count
     is zero *because nothing was compared*, which is indistinguishable from zero because everything
     is current. `current_revision` is echoed back and is the ONLY thing separating them. A screen
     that prints "0 stale" without reading it reports a check that never ran.

Both are asserted against the live route rather than argued, because a screen that relies on them is
relying on behaviour, not on this docstring.

Run from services/api:
  PYTHONPATH=src:../data/src AEC_TRUST_XUSER=1 ./.venv/bin/python test_scenario_provenance.py
"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

os.environ["DATABASE_URL"] = "sqlite:///./test_scenario_provenance.db"
os.environ["STORAGE_DIR"] = "./test_storage_scprov"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_scenario_provenance.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.cited_answer import cite_doc  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED = []
HDR = {"X-User": "underwriter"}


def check(label, ok, detail=None):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


#: A complete, solvable deal. The material PATHS are read back from the route rather than assumed
#: here: the engine walks numeric leaves under its own MATERIAL_ROOTS, and a test that hardcoded the
#: list would be asserting this fixture's shape rather than the engine's rule.
_BASE = {
    "timing": {"construction_months": 18, "leaseup_months": 6, "hold_years": 7, "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront"},
        {"category": "hard", "name": "Hard costs", "amount": 18_000_000, "curve": "scurve"},
    ],
    "debt": {"ltc": 0.6, "rate": 0.075, "points": 0.01},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 3_600_000, "other_income_annual": 200_000,
                   "opex_annual": 1_300_000, "reserves_annual": 90_000,
                   "stabilized_occ": 0.94, "credit_loss_pct": 0.01},
    "exit": {"exit_cap": 0.055, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": 0.08, "lp": 0.9, "gp": 0.1}, {"hurdle": None, "lp": 0.8, "gp": 0.2}]},
    "discount_rate": 0.10,
}


def assumptions(sources: dict | None = None) -> dict:
    import copy
    a = copy.deepcopy(_BASE)
    if sources is not None:
        a["sources"] = sources
    return a


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "SCENARIO-SOURCES"}, headers=HDR).json()["id"]

    def scenario(name: str, sources: dict | None = None) -> str:
        r = c.post("/proforma/scenarios", headers=HDR,
                   json={"name": name, "project_id": pid, "assumptions": assumptions(sources)})
        assert r.status_code in (200, 201), r.text[:300]
        return r.json()["id"]

    def prov(sid: str, revision: str | None = None) -> dict:
        q = f"?revision={revision}" if revision else ""
        r = c.get(f"/proforma/scenarios/{sid}/provenance{q}", headers=HDR)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    # --- 0. the population is the material numeric drivers, and gaps are NAMED --------------------
    bare = prov(scenario("No sources at all"))
    check("a scenario with no sources has material assumptions and zero coverage",
          bare["material_count"] > 0 and bare["cited_count"] == 0 and bare["coverage_pct"] == 0.0,
          (bare["material_count"], bare["cited_count"], bare["coverage_pct"]))
    check("...and the gaps are NAMED, not merely counted — the actionable half",
          sorted(bare["uncited"]) == sorted(bare["uncited"]) and len(bare["uncited"]) == bare["uncited_count"]
          and all("." in p for p in bare["uncited"]),
          bare["uncited"])
    _paths = set(bare["uncited"])
    check("...and the drivers an underwriter would argue about are among them",
          {"operations.potential_rent_annual", "exit.exit_cap", "debt.ltc"} <= _paths,
          sorted(_paths))
    check("...while `cost_lines` is NOT — boe_ledger owns those, and double-counting would pad coverage",
          not any(p.startswith("cost_lines") for p in _paths), sorted(_paths))

    # --- 1. HAZARD ONE: 100% COVERAGE WITH EVERY CITATION STALE -----------------------------------
    # Every material path cited, every citation naming rev-1, then asked about rev-9.
    _all_cited = {p: [cite_doc("appraisal.pdf", revision="rev-1", page=12)] for p in _paths}
    stale_sid = scenario("Fully cited, all stale", _all_cited)

    fresh_eyes = prov(stale_sid, revision="rev-9")
    check("every material assumption is cited — coverage reads 100%",
          fresh_eyes["coverage_pct"] == 100.0 and fresh_eyes["uncited_count"] == 0,
          (fresh_eyes["coverage_pct"], fresh_eyes["uncited"]))
    check("...AND every one of those citations is stale against the current revision",
          fresh_eyes["stale_citation_count"] == len(_paths),
          (fresh_eyes["stale_citation_count"], len(_paths)))
    check("...so COVERAGE AND CURRENCY ARE INDEPENDENT: 100% says nothing about currency",
          fresh_eyes["coverage_pct"] == 100.0 and fresh_eyes["stale_citation_count"] > 0)
    check("...and the rows still say `cited`, which is why the screen must carry the second axis",
          all(r["status"] == "cited" for r in fresh_eyes["assumptions"]),
          [r["status"] for r in fresh_eyes["assumptions"]])

    # --- 2. HAZARD TWO: THE ZERO THAT MEANS "NOT CHECKED" -----------------------------------------
    # The SAME scenario, asked WITHOUT a revision. Nothing about the data changed.
    no_rev = prov(stale_sid)
    check("with no ?revision=, the same all-stale scenario reports ZERO stale citations",
          no_rev["stale_citation_count"] == 0, no_rev["stale_citation_count"])
    check("...while the data is identical — coverage and cited count are unchanged",
          no_rev["coverage_pct"] == fresh_eyes["coverage_pct"]
          and no_rev["cited_count"] == fresh_eyes["cited_count"])
    check("...so the two zeroes are indistinguishable FROM THE COUNT ALONE",
          no_rev["stale_citation_count"] == 0,
          "if this ever differs, the engine started computing staleness without a revision")
    check("...and `current_revision` is what separates them: null here, set there",
          no_rev["current_revision"] is None and fresh_eyes["current_revision"] == "rev-9",
          (no_rev["current_revision"], fresh_eyes["current_revision"]))

    # The genuinely-current case, so "all-current" is a state the route really produces and not just
    # one the client invents. Without this, a screen could map every supplied revision to "stale".
    current_sid = scenario("Fully cited, all current",
                           {p: [cite_doc("appraisal.pdf", revision="rev-9", page=12)] for p in _paths})
    current = prov(current_sid, revision="rev-9")
    check("a scenario whose citations DO name the current revision reports zero stale, with a revision set",
          current["stale_citation_count"] == 0 and current["current_revision"] == "rev-9"
          and current["coverage_pct"] == 100.0, current)

    # --- 3. UNCITED AND MALFORMED ARE DIFFERENT ACTIONS, and a path can be BOTH --------------------
    # A DICT that is not a citation. The obvious fixture -- a bare string where a citation belongs --
    # cannot reach the engine at all: `Assumptions.sources` is typed `dict[str, list[dict]]`, so
    # pydantic 422s it at the boundary. That is the type doing its job, and it narrows the reachable
    # malformed case to the one `cited_answer.is_citation` was written for: a dict that declares
    # nothing the contract can resolve. Its docstring records that an EMPTY dict once scored this
    # module 100% coverage.
    broken_sid = scenario("A source that is not a citation",
                          {"exit.exit_cap": [{"note": "see the appraisal"}]})
    broken = prov(broken_sid)
    check("a recorded entry that is not a readable citation counts as UNCITED",
          "exit.exit_cap" in broken["uncited"], broken["uncited"])
    check("...and is ALSO named as malformed — the caller believes it is sourced and it is not",
          "exit.exit_cap" in broken["malformed_citation_paths"]
          and broken["malformed_citation_count"] >= 1, broken)
    check("...so the same path appears in BOTH lists, which is why a screen must not merge them",
          "exit.exit_cap" in broken["uncited"] and "exit.exit_cap" in broken["malformed_citation_paths"])

    # --- 4. ORPHANED SOURCES: a citation pointing at nothing ---------------------------------------
    orphan_sid = scenario("A citation against a path that is not an assumption",
                          {"exit.exit_cpa": [cite_doc("appraisal.pdf", revision="rev-9")]})
    orphan = prov(orphan_sid)
    check("a citation keyed to a non-assumption path is reported as orphaned",
          "exit.exit_cpa" in orphan["orphaned_sources"], orphan["orphaned_sources"])
    check("...and does NOT inflate coverage — the real exit.exit_cap is still uncited",
          "exit.exit_cap" in orphan["uncited"] and orphan["coverage_pct"] < 100.0,
          (orphan["uncited"], orphan["coverage_pct"]))

print()
if FAILED:
    print(f"scenario_provenance: {len(FAILED)} FAILED — {FAILED}")
    raise SystemExit(1)
print("scenario_provenance: all checks passed — coverage and citation CURRENCY are independent (100% "
      "coverage with every citation stale is a real, reachable state), a zero stale-count means "
      "'not checked' whenever `current_revision` is null and 'all current' when it is set, uncited "
      "and malformed are separate lists that can name the same path, and an orphaned citation does "
      "not inflate coverage.")
