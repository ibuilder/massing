"""R22-PROVENANCE — one admissibility verdict, and the score it refuses to compute.

Premise-checked: two of three legs were already built (`cited_answer`, `boe_ledger`) and
`assumption_provenance` closed the third. **The join did not exist** — provenance was exposed only
on the proforma path, so nothing answered "is this deal's output admissible?" without a reader
opening three endpoints and reconciling them.

The assertions, and the second is the one the code exists for:

1. **there is no blended score.** A single 0–100 lets a well-cited proforma hide an uncited
   estimate, and a memo is not admissible because it scored 82. Per-leg verdicts, named blockers;
2. **an empty leg is `no_data`, never coverage — and the two real engines disagree about zero, in
   opposite directions.** `boe_ledger.ledger([])` reports `pct_documented 1.0` ("perfect") and
   `assumption_provenance.provenance({})` reports `coverage_pct 0.0` ("nothing"). Both describe the
   same absence. Averaging them is arithmetic across two different claims, and either alone
   misleads: a project with no estimate lines is not one with a perfectly documented estimate;
3. **blockers are NAMED, not counted** — a count gets quoted in a memo, a list gets fixed;
4. **the twin of every refusal**: a fully-cited deal must actually come back `admissible`, or the
   verdict is just a machine for saying no.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_provenance_report.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import assumption_provenance, boe_ledger  # noqa: E402
from aec_api.provenance_report import (  # noqa: E402
    STATUS_GAPS,
    STATUS_NO_DATA,
    STATUS_OK,
    VERDICT_ADMISSIBLE,
    VERDICT_BLOCKED,
    VERDICT_INCOMPLETE,
    report,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def leg(r, name):
    return next(x for x in r["legs"] if x["leg"] == name)


# --- 2. THE TWO REAL ENGINES DISAGREE ABOUT ZERO — asserted against them, not assumed ----------------
empty_ledger = boe_ledger.ledger([])
empty_assump = assumption_provenance.provenance({})
check("boe_ledger reports an EMPTY ledger as 100% documented",
      empty_ledger["pct_documented"] == 1.0, empty_ledger["pct_documented"])
check("assumption_provenance reports NO assumptions as 0% coverage",
      empty_assump["coverage_pct"] == 0.0, empty_assump["coverage_pct"])
check("  they describe the SAME absence with opposite numbers — which is why no average is taken",
      empty_ledger["pct_documented"] != empty_assump["coverage_pct"])

r = report(empty_assump, empty_ledger, [])
check("an empty estimate leg is no_data, NOT 'perfectly documented'",
      leg(r, "estimate")["status"] == STATUS_NO_DATA, leg(r, "estimate"))
check("  and the reason names the 1.0 that would have misled",
      "perfectly" in leg(r, "estimate")["note"], leg(r, "estimate")["note"])
check("an empty assumptions leg is no_data, NOT '0% cited'",
      leg(r, "assumptions")["status"] == STATUS_NO_DATA, leg(r, "assumptions"))
check("  distinguishing 'nothing to cite' from 'nothing cited'",
      "not 'nothing cited'" in leg(r, "assumptions")["note"], leg(r, "assumptions")["note"])
check("a deal with NO data anywhere is INCOMPLETE, not admissible",
      r["verdict"] == VERDICT_INCOMPLETE, r["verdict"])
check("  and says a deal with nothing in it must not read like a clean one",
      "nothing in it" in r["reason"], r["reason"])

# --- 1. NO BLENDED SCORE ------------------------------------------------------------------------------
check("the report carries NO overall percentage or score field",
      not any(k for k in r if "score" in k.lower() or "pct" in k.lower()), sorted(r))
check("  and says why a single number would be wrong",
      "hide an uncited estimate" in r["note"], r["note"])

# --- 3. BLOCKERS ARE NAMED -----------------------------------------------------------------------------
LED = boe_ledger.ledger([
    {"cost_code": "03-30-00", "description": "concrete", "qty": 10, "unit_cost": 100, "source": "quote",
     "quote_ref": "Q-1", "basis_date": "2026-01-01", "escalation_pct": 3, "contingency_pct": 5},
    {"cost_code": "05-12-00", "description": "steel", "qty": 5, "unit_cost": 900},
])
gaps = report(empty_assump, LED, [{"text": "IRR is 18%", "citations": []},
                                  {"text": "cap rate 5%", "citations": [{"source_type": "doc"}]}])
check("a deal with uncited items is BLOCKED", gaps["verdict"] == VERDICT_BLOCKED, gaps["verdict"])
check("  the undocumented line is NAMED by its COST CODE, with what it is missing",
      any("05-12-00" in u for u in leg(gaps, "estimate")["uncited"]), leg(gaps, "estimate")["uncited"])
check("  the documented line is not named", not any("03-30-00" in u for u in leg(gaps, "estimate")["uncited"]))
check("  the uncited agent answer is NAMED",
      leg(gaps, "answers")["uncited"] == ["IRR is 18%"], leg(gaps, "answers")["uncited"])
check("  the CITED answer is not named", leg(gaps, "answers")["counted"] == 2
      and leg(gaps, "answers")["uncited_count"] == 1, leg(gaps, "answers"))
check("  blocking legs are listed", set(gaps["blocking_legs"]) == {"estimate", "answers"},
      gaps["blocking_legs"])
check("  with the total across legs", gaps["uncited_total"] == 2, gaps["uncited_total"])
check("  and the reason says a count gets quoted while a list gets fixed",
      "a list gets fixed" in gaps["reason"], gaps["reason"])

# --- 4. THE TWIN — a clean deal MUST come back admissible ------------------------------------------------
CLEAN_LED = boe_ledger.ledger([
    {"cost_code": "03-30-00", "description": "concrete", "qty": 10, "unit_cost": 100, "source": "quote",
     "quote_ref": "Q-1", "basis_date": "2026-01-01", "escalation_pct": 3, "contingency_pct": 5}])
CLEAN_ASSUMP = {"material_count": 4, "uncited": [], "coverage_pct": 100.0}
ok = report(CLEAN_ASSUMP, CLEAN_LED, [{"text": "cap rate 5%", "citations": [{"source_type": "doc"}]}])
check("A FULLY CITED DEAL IS ADMISSIBLE — the verdict is not just a machine for saying no",
      ok["verdict"] == VERDICT_ADMISSIBLE, ok)
check("  every leg reports cited", all(x["status"] == STATUS_OK for x in ok["legs"]),
      [(x["leg"], x["status"]) for x in ok["legs"]])
check("  and nothing is named as a blocker",
      ok["uncited_total"] == 0 and ok["blocking_legs"] == [], ok)

# a leg that is CLEAN but another absent -> incomplete, never admissible
part = report(CLEAN_ASSUMP, CLEAN_LED, [])
check("all present legs clean but one absent is INCOMPLETE, not admissible",
      part["verdict"] == VERDICT_INCOMPLETE, part["verdict"])
check("  naming which leg is empty", part["legs_absent"] == ["answers"], part["legs_absent"])
check("  and saying an absent leg is not a clean one",
      "absent leg is not a clean one" in part["reason"], part["reason"])

# --- gaps outrank absence: a blocked leg must not be softened by an empty one ----------------------------
mix = report(CLEAN_ASSUMP, LED, [])
check("uncited items BLOCK even when another leg is merely absent",
      mix["verdict"] == VERDICT_BLOCKED, mix["verdict"])
check("  a partially-cited assumptions leg is has_uncited, not no_data",
      leg(report({"material_count": 3, "uncited": ["exit.exit_cap"]}, CLEAN_LED,
                 [{"text": "x", "citations": [{"s": 1}]}]), "assumptions")["status"] == STATUS_GAPS)
check("nothing supplied at all is INCOMPLETE, not a crash", report()["verdict"] == VERDICT_INCOMPLETE)

# --- PROJECT-SCOPED (slice 2): only ONE leg is gatherable, and saying which is the point -------------
# `not_captured` must be distinct from `no_data`. "You have not filled this in" and "this system has
# nowhere to put it" send a reader to different places — one fills a field, the other changes a
# schema — and a verdict that conflates them wastes the time of whoever acts on it.
import os as _os  # noqa: E402

_os.environ["DATABASE_URL"] = "sqlite:///./test_provenance_report.db"
_os.environ["STORAGE_DIR"] = "./test_storage_prov"
_os.environ.pop("AEC_RBAC", None)
for _f in ("./test_provenance_report.db",):
    if _os.path.exists(_f):
        _os.remove(_f)

from aec_api import provenance_report as _pr  # noqa: E402
from aec_api.db import Base as _Base, SessionLocal as _SL, engine as _eng  # noqa: E402
from aec_api.models import Project as _P, Scenario as _S  # noqa: E402

_Base.metadata.create_all(_eng)
with _SL() as _db:
    _db.add(_P(id="pp1", name="Prov"))
    _db.add(_S(id="s1", project_id="pp1", name="Base case",
               assumptions={"exit": {"exit_cap": 0.055}, "debt": {"ltc": 0.6}}))
    _db.commit()
    FP = _pr.from_project(_db, "pp1")
    EMPTY = _pr.from_project(_db, "no-project")

check("from_project finds the project's scenario", FP["scenario_id"] == "s1", FP.get("scenario_id"))
check("  the ASSUMPTIONS leg is real — gathered, not supplied",
      leg(FP, "assumptions")["status"] in (STATUS_OK, STATUS_GAPS), leg(FP, "assumptions"))
check("THE ESTIMATE LEG IS not_captured, NOT no_data",
      leg(FP, "estimate")["status"] == _pr.STATUS_NOT_CAPTURED, leg(FP, "estimate")["status"])
check("  and names the exact columns that would make it gatherable",
      all(k in leg(FP, "estimate")["note"] for k in ("quote_ref", "basis_date")),
      leg(FP, "estimate")["note"])
check("THE ANSWERS LEG IS not_captured — agent answers are never persisted",
      leg(FP, "answers")["status"] == _pr.STATUS_NOT_CAPTURED, leg(FP, "answers")["status"])
check("  naming what would make it gatherable", "store of answered claims"
      in leg(FP, "answers")["note"], leg(FP, "answers")["note"])
check("the two are LISTED separately from absent legs",
      FP["legs_not_captured"] == ["estimate", "answers"], FP.get("legs_not_captured"))

check("A PROJECT VERDICT CANNOT READ admissible TODAY — and says why",
      FP["verdict"] != VERDICT_ADMISSIBLE, FP["verdict"])
check("  attributing it to the SCHEMA, not to the deal",
      "statement about this schema, not about the deal" in FP["note"], FP["note"][:120])
check("  which is the honest alternative to scoring only the leg that works",
      "hidden by scoring only the leg" in FP["note"])

check("a project with no scenario still answers, rather than erroring",
      EMPTY["scenario_id"] is None and EMPTY["verdict"] == VERDICT_INCOMPLETE, EMPTY["verdict"])
check("  its assumptions leg is no_data — a source EXISTS and is empty",
      leg(EMPTY, "assumptions")["status"] == STATUS_NO_DATA, leg(EMPTY, "assumptions")["status"])
check("  so no_data and not_captured coexist in one report, meaning different things",
      {leg(EMPTY, "assumptions")["status"], leg(EMPTY, "estimate")["status"]}
      == {STATUS_NO_DATA, _pr.STATUS_NOT_CAPTURED},
      [(x["leg"], x["status"]) for x in EMPTY["legs"]])

_eng.dispose()
for _f in ("./test_provenance_report.db",):
    if _os.path.exists(_f):
        try:
            _os.remove(_f)
        except OSError:
            pass

print()
if FAILED:
    print(f"provenance_report: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("provenance_report: all checks passed")
