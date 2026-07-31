"""R22-PROVENANCE ② — which deal assumptions carry a source, and the ways that can be faked.

The interesting assertions here are the ones about the DENOMINATOR. A coverage percentage is the kind
of number that reaches an investment committee, and there are three cheap ways to make it look good
that this module has to refuse:

1. counting every key, so trivially-cited switches drown an uncited exit cap;
2. counting a citation aimed at a path that does not exist;
3. reporting a percentage with no named gaps, so nobody can act on it.

Plus the regression that made the field necessary at all: a `sources` block used to be accepted with
a 200 and then silently dropped before storage.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_assumption_provenance.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import assumption_provenance as ap  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def cite(doc="appraisal.pdf", page=12, revision="B"):
    return {"source_type": "doc", "document_id": doc, "page": page, "revision": revision}


DEAL = {
    "timing": {"construction_months": 6, "leaseup_months": 3, "hold_years": 2,
               "start_date": "2026-01-01"},
    "cost_lines": [{"category": "hard", "name": "Build", "amount": 4_000_000}],
    "debt": {"ltc": 0.6, "rate": 0.08, "points": 0.01, "funding": "equity_first"},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 700_000, "other_income_annual": 0,
                   "opex_annual": 250_000, "stabilized_occ": 0.95, "credit_loss_pct": 0.02},
    "exit": {"exit_cap": 0.06, "selling_cost_pct": 0.02},
    # `tiers` is REQUIRED by the Assumptions model — omitting it passed every pure-function check
    # here and only failed at the pydantic boundary in section 7. A fixture that never reaches a
    # validator is a fixture whose shape nobody has checked.
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]},
}

# --- 1. the denominator is the MATERIAL assumptions, not every key ---------------------------------------
paths = ap.material_paths(DEAL)
check("the driver paths use the SAME dotted scheme sensitivity/monte_carlo address",
      "operations.potential_rent_annual" in paths and "exit.exit_cap" in paths, paths[:6])
check("switches are excluded — citing 'american' is not a claim about a number",
      not any(p.endswith((".style", ".funding", ".clawback")) for p in paths), paths)
check("cost lines are excluded — boe_ledger already owns their provenance",
      not any(p.startswith("cost_lines") for p in paths), paths)
check("a date is not counted as a numeric driver",
      "timing.start_date" not in paths, paths)
check("but real quantities are", {"debt.ltc", "debt.rate", "equity.lp_pct",
                                  "waterfall.pref_rate"} <= set(paths), sorted(paths))

# --- 2. an uncited assumption is NAMED, not just counted -------------------------------------------------
none_cited = ap.provenance(DEAL)
check("with no sources at all, coverage is 0%", none_cited["coverage_pct"] == 0.0,
      none_cited["coverage_pct"])
check("  and every material assumption is listed as uncited",
      none_cited["uncited_count"] == len(paths) and len(none_cited["uncited"]) == len(paths))
check("  the note says absence of a source is not a judgement about the value",
      "not a judgement" in none_cited["note"] or "not a pass" in none_cited["note"],
      none_cited["note"])
check("  an uncited row says so explicitly rather than omitting the field",
      all(r["status"] == ap.STATUS_UNCITED for r in none_cited["assumptions"]))

# --- 3. citing the drivers moves coverage, and only for those drivers ------------------------------------
sourced = {**DEAL, "sources": {"exit.exit_cap": [cite()],
                               "operations.potential_rent_annual": [cite("rent_roll.pdf", 3)]}}
p2 = ap.provenance(sourced)
check("citing two drivers gives exactly two cited", p2["cited_count"] == 2, p2["cited_count"])
check("  coverage is those two over the material set, not over 'sources'",
      p2["coverage_pct"] == round(100 * 2 / len(paths), 1), p2["coverage_pct"])
check("  the exit cap row carries its citation", next(
    r for r in p2["assumptions"] if r["path"] == "exit.exit_cap")["citations"][0]["page"] == 12)
check("  and the rest remain named as uncited",
      "debt.ltc" in p2["uncited"] and len(p2["uncited"]) == len(paths) - 2)

# --- 4. a citation aimed at a path that does not exist cannot inflate coverage ---------------------------
# This is the cheapest way to fake the number: cite freely against paths nobody checks.
bogus = {**DEAL, "sources": {"operations.rent": [cite()],            # typo — the path is potential_rent_annual
                             "exit.cap_rate": [cite()],              # renamed away
                             "exit.exit_cap": [cite()]}}
p3 = ap.provenance(bogus)
check("citations against non-existent paths do NOT count as coverage",
      p3["cited_count"] == 1, p3["cited_count"])
check("  and they are reported as orphaned rather than ignored",
      sorted(p3["orphaned_sources"]) == ["exit.cap_rate", "operations.rent"],
      p3["orphaned_sources"])
check("  so three 'sources' entries cannot read as three cited assumptions",
      len(bogus["sources"]) == 3 and p3["cited_count"] == 1)

# --- 5. a stale revision is counted, reusing cited_answer's signal ---------------------------------------
stale = {**DEAL, "sources": {"exit.exit_cap": [cite(revision="A")]}}
p4 = ap.provenance(stale, current_revision="C")
check("a citation against an older revision is flagged stale",
      p4["stale_citation_count"] == 1, p4["stale_citation_count"])
check("  the assumption still counts as cited — stale is not absent",
      p4["cited_count"] == 1, p4["cited_count"])
fresh = ap.provenance({**DEAL, "sources": {"exit.exit_cap": [cite(revision="C")]}},
                      current_revision="C")
check("  a current-revision citation is not flagged", fresh["stale_citation_count"] == 0)
check("  and confidence comes from cited_answer, not a second invented scale",
      isinstance(next(r for r in fresh["assumptions"]
                      if r["path"] == "exit.exit_cap")["confidence"], (int, float)))

# --- 6. a single citation dict is accepted as well as a list ---------------------------------------------
check("a bare citation dict is treated as one citation, not silently dropped",
      ap.provenance({**DEAL, "sources": {"exit.exit_cap": cite()}})["cited_count"] == 1)
check("an empty citation list is UNCITED, not cited",
      ap.provenance({**DEAL, "sources": {"exit.exit_cap": []}})["cited_count"] == 0)
check("a malformed citation entry does not crash and does not count",
      ap.provenance({**DEAL, "sources": {"exit.exit_cap": ["not a dict"]}})["cited_count"] == 0)

# --- 7. THE REGRESSION: the schema must let `sources` survive the write path -----------------------------
# Before this field existed, pydantic v2's default `extra="ignore"` accepted a sources block with a
# 200 and dropped it in model_dump() — the caller could not tell their provenance had been discarded.
from aec_api.routers.proforma_schemas import Assumptions  # noqa: E402

dumped = Assumptions(**sourced).model_dump()
check("`sources` survives Assumptions.model_dump() — it used to be silently dropped",
      "sources" in dumped and dumped["sources"] is not None, sorted(dumped)[:6])
check("  and the citation is intact, not merely the key",
      dumped["sources"]["exit.exit_cap"][0]["page"] == 12, dumped.get("sources"))
check("  a deal with no sources still dumps cleanly as None",
      Assumptions(**DEAL).model_dump()["sources"] is None)
# and the round trip a stored scenario actually takes
check("provenance reads what model_dump produced, end to end",
      ap.provenance(dumped)["cited_count"] == 2, ap.provenance(dumped)["cited_count"])


# --- 8. the scenario wrapper carries identity so a figure is traceable to its deal -----------------------
class _Scenario:
    id, name = "s1", "Base case"
    assumptions = sourced


sp = ap.scenario_provenance(_Scenario(), current_revision="B")
check("scenario provenance names the scenario", (sp["scenario_id"], sp["scenario_name"])
      == ("s1", "Base case"), (sp["scenario_id"], sp["scenario_name"]))
check("  and reports the same coverage as the pure function",
      sp["coverage_pct"] == p2["coverage_pct"])
check("a scenario with no assumptions says so rather than dividing by zero",
      ap.provenance({})["coverage_pct"] == 0.0
      and ap.provenance({})["message"] is not None)

print()
if FAILED:
    print(f"assumption_provenance: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("assumption_provenance: all checks passed")
