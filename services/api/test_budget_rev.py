"""PROFORMA-CONCURRENCY: the lock made the WRITE atomic and left the REQUEST stale.

Two findings, both confirmed on PR #557 and both declined there as pre-existing rather than
regressions of that diff. They are the same mistake in two shapes, and the shape is the one this
tree keeps re-learning: **a lock orders writers; it does not tell the second one that what it read
is out of date.**

(A) `put_dev_budget` replaces the WHOLE `dev_budget` blob. An editor whose screen loaded before a
    `sync-gmp` or `sync-from-model` click saves the hard lines that sync had just replaced, and both
    calls return 200. Serialising them changes nothing: the stale body is applied *after* the sync,
    in perfect order, and the sync is gone.

    **The comment that stood over that lock justified it by saying the two edits touch DIFFERENT
    line categories, so serialising lets both survive.** That is `connections.update_connection`'s
    argument, and it is true THERE because that route merges keys into the blob. This one assigns
    over it. *A justification copied from the route that inspired the control describes that route*
    -- and it reads as settled precisely because it is true somewhere.

(B) `sync_model_to_hard` reads the IFC, spends a full geometry takeoff on it, and commits a hard
    cost derived from it. The read is outside the lock, correctly -- holding the project lock across
    a takeoff would block every publication for as long as the parse runs. The cost is that a
    publication can land in between, and the committed number then describes a model the project no
    longer has, under a 200 saying "synced".

    **And the obvious check cannot work.** `publish_source_ifc` writes the new model to a unique
    staged path and `os.replace`s it onto the SAME final path, so `Project.source_ifc` is re-assigned
    the string it already held. Comparing it passes on exactly the interleaving it would exist to
    catch. *A staleness check against a field the writer does not move always passes, and reads as
    though it were guarding something.* `authoring_shared.ifc_identity` compares the inode instead,
    which `os.replace` always changes.

Every fix here is mutation-checked: for each, the guard is disabled in the way a future edit would
plausibly break it, and the ORIGINAL defect must come back. A check that still passes with the guard
removed is not testing the guard.

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_budget_rev.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./_budgetrev_test.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_budgetrev")
os.environ.setdefault("AEC_TRUST_XUSER", "1")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import pathlib  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from aec_api import dev_budget as dvb  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_api.routers import authoring_shared as ash  # noqa: E402
from aec_api.routers import proforma as pf  # noqa: E402

Base.metadata.create_all(engine)

PID = "budget-rev-test"
FRESH = "budget-rev-fresh"          # never had a budget saved -- the starter-vs-column case
ACTOR = "tester"
WORK = pathlib.Path(tempfile.mkdtemp(prefix="budget_rev_")).resolve()

FAILED: list[str] = []


def check(label: str, ok, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}   {detail}")
    if not ok:
        FAILED.append(label)


def reset(pid: str = PID, budget: dict | None = None) -> None:
    db = SessionLocal()
    db.query(Project).filter(Project.id == pid).delete()
    db.add(Project(id=pid, name=pid, dev_budget=budget))
    db.commit()
    db.close()


def status_of(exc: BaseException) -> int | None:
    return exc.status_code if isinstance(exc, HTTPException) else None


# ---------------------------------------------------------------------------------------------
# A1. `budget_rev` itself.
# ---------------------------------------------------------------------------------------------
B1 = {"lines": [{"category": "hard", "description": "GMP", "unit_cost": 100.0, "quantity": 1}],
      "contingency": {"hard": 0.1, "soft": 0.1}}
B1_REORDERED = {"contingency": {"soft": 0.1, "hard": 0.1},
                "lines": [{"quantity": 1, "unit_cost": 100.0, "description": "GMP", "category": "hard"}]}
B2 = {"lines": [{"category": "hard", "description": "GMP", "unit_cost": 101.0, "quantity": 1}],
      "contingency": {"hard": 0.1, "soft": 0.1}}

check("`budget_rev` is stable under key ORDER -- a re-serialisation that reorders keys is not an "
      "edit, and a token that said it was would 409 on a round-trip that changed nothing",
      dvb.budget_rev(B1) == dvb.budget_rev(B1_REORDERED),
      f"{dvb.budget_rev(B1)} vs {dvb.budget_rev(B1_REORDERED)}")
check("...and it MOVES on a one-cent change, or the precondition can never fire",
      dvb.budget_rev(B1) != dvb.budget_rev(B2))

# ---------------------------------------------------------------------------------------------
# A2. The starter-budget case: `get_dev_budget` returns `p.dev_budget or starter_budget()`, so on a
#     project that has never saved one the caller holds the STARTER while the column holds None. A
#     token taken from the column would never match the one the client echoes, and every FIRST save
#     would 409. The mismatch is not in the comparison -- it is in disagreeing about what was read.
# ---------------------------------------------------------------------------------------------
reset(FRESH, budget=None)
_db = SessionLocal()
_got = pf.get_dev_budget(FRESH, db=_db, _sec=ACTOR)
check("a project with NO saved budget still gets a `rev`, and it is the rev of the STARTER budget "
      "the caller was shown rather than of the NULL column",
      _got["rev"] == dvb.budget_rev(dvb.starter_budget()) and _got["rev"] == dvb.budget_rev(_got["budget"]),
      f"rev={_got['rev']}")
_first = pf.put_dev_budget(FRESH, pf.DevBudgetIn(**B1, rev=_got["rev"]), db=_db, _sec=ACTOR)
check("  ...so the FIRST save echoing that rev is accepted, not refused",
      _first["summary"]["grand_total"] > 0 and _first["rev"] == dvb.budget_rev(B1),
      f"rev={_first['rev']}")
_db.close()

# ---------------------------------------------------------------------------------------------
# A3. Matching rev accepted, stale rev refused, absent rev allowed.
# ---------------------------------------------------------------------------------------------
reset(budget=B1)
_db = SessionLocal()
rev0 = pf.get_dev_budget(PID, db=_db, _sec=ACTOR)["rev"]
r1 = pf.put_dev_budget(PID, pf.DevBudgetIn(**B2, rev=rev0), db=_db, _sec=ACTOR)
check("a PUT carrying the rev it was shown is accepted and hands back the NEW rev",
      r1["rev"] == dvb.budget_rev(B2) and r1["rev"] != rev0, f"{rev0} -> {r1['rev']}")

_stale = None
try:
    pf.put_dev_budget(PID, pf.DevBudgetIn(**B1, rev=rev0), db=_db, _sec=ACTOR)
except BaseException as e:      # noqa: BLE001 -- the status is the assertion
    _stale = e
check("...and replaying that now-stale rev is a 409, not a silent overwrite",
      status_of(_stale) == 409, f"raised={_stale!r}")

_no_rev = pf.put_dev_budget(PID, pf.DevBudgetIn(**B1), db=_db, _sec=ACTOR)
check("a PUT with NO rev is still accepted -- the documented boundary, kept for the "
      "whole-budget writers that race nothing (`build_demo_data.py`, `e2e_dome.py`, "
      "`e2e_vertfarm.py`); the caller that DOES race is pinned by the web-source check below",
      _no_rev["rev"] == dvb.budget_rev(B1), f"rev={_no_rev['rev']}")
_db.close()


# ---------------------------------------------------------------------------------------------
# A4. THE DEFECT ITSELF: a form loaded before a sync, saved after it.
# ---------------------------------------------------------------------------------------------
SOFT_ONLY = {"lines": [{"category": "soft", "description": "Architect", "unit_cost": 50_000.0, "quantity": 1}],
             "contingency": {"hard": 0.1, "soft": 0.1}}


def form_then_sync(*, guard: bool) -> tuple[int | None, list[dict]]:
    """Load the budget form, let a GMP sync commit, then save the form. Returns (status, hard lines).

    `guard=False` reinstates the pre-fix behaviour by making every rev compare EQUAL -- a token that
    cannot distinguish two budgets is a route with no precondition, which is what this one was.

    **The patch has to cover the GET as well as the PUT, and the first draft of it did not.** Leaving
    `get_dev_budget` on the real function and neutering only the route's side made the two sides
    disagree *more*, so the mutation still 409'd and reported PASS-shaped green for the wrong reason
    -- it was testing that a mismatch is refused, which is the check above. *A mutation has to break
    the property under test, not merely perturb an input to it.*
    """
    reset(budget=SOFT_ONLY)
    real = dvb.budget_rev
    if not guard:
        dvb.budget_rev = lambda _b: "same"
    db = SessionLocal()
    shown = pf.get_dev_budget(PID, db=db, _sec=ACTOR)          # the editor's screen loads
    body = dict(shown["budget"])
    body["lines"] = [*body["lines"], {"category": "soft", "description": "Survey",
                                      "unit_cost": 4_000.0, "quantity": 1}]

    other = SessionLocal()                                     # ...meanwhile, someone clicks Sync GMP
    p = other.get(Project, PID)
    synced = dict(p.dev_budget or {})
    synced["lines"] = [*(synced.get("lines") or []),
                       {"category": "hard", "description": "Construction — GC GMP (synced)",
                        "unit_cost": 9_000_000.0, "quantity": 1, "cost_code": ""}]
    p.dev_budget = synced
    other.commit()
    other.close()

    status = None
    try:
        pf.put_dev_budget(PID, pf.DevBudgetIn(lines=body["lines"], contingency=body["contingency"],
                                              rev=shown["rev"]), db=db, _sec=ACTOR)
        status = 200
    except BaseException as e:                                 # noqa: BLE001
        status = status_of(e)
    finally:
        dvb.budget_rev = real
    db.close()

    after = SessionLocal()
    kept = [ln for ln in (after.get(Project, PID).dev_budget or {}).get("lines", [])
            if ln.get("category") == "hard"]
    after.close()
    return status, kept


_st, _hard = form_then_sync(guard=True)
check("THE DEFECT: a budget form saved after a GMP sync is REFUSED (409) and the $9,000,000 synced "
      "hard line survives -- the lock alone ordered these two perfectly and still lost it",
      _st == 409 and len(_hard) == 1, f"status={_st} hard_lines={_hard}")

_st, _hard = form_then_sync(guard=False)
check("MUTATION: with the rev comparison neutered the same sequence returns 200 and the synced hard "
      "line is GONE -- the pre-fix behaviour, reproduced rather than described",
      _st == 200 and _hard == [], f"status={_st} hard_lines={_hard}")


# ---------------------------------------------------------------------------------------------
# B1. `ifc_identity` and why `Project.source_ifc` cannot do this job.
# ---------------------------------------------------------------------------------------------
FINAL = WORK / "source.ifc"
FINAL.write_bytes(b"ISO-10303-21;\n/* MODEL A */\nEND-ISO-10303-21;\n")
_before = ash.ifc_identity(FINAL)
_staged = WORK / "staged.ifc"
_staged.write_bytes(b"ISO-10303-21;\n/* MODEL B -- republished */\nEND-ISO-10303-21;\n")
os.replace(_staged, FINAL)                                     # exactly what `publish_source_ifc` does
_after = ash.ifc_identity(FINAL)

check("`ifc_identity` MOVES across an `os.replace` onto the same path -- which is the only thing a "
      "publication does to the file",
      _before is not None and _after is not None and _before != _after, f"{_before} -> {_after}")
#: The counterpart, and it has to be asserted against a real ROW rather than against the path
#: literal -- `str(FINAL) == str(FINAL)` was the first draft of this line, which is a check that
#: cannot fail dressed as one that can. What matters is the value a naive guard would compare:
#: the column, re-read after the publication.
reset(budget=SOFT_ONLY)
_db = SessionLocal()
_p = _db.get(Project, PID)
_p.source_ifc = str(FINAL)
_db.commit()
_col_before = _p.source_ifc
_staged2 = WORK / "staged2.ifc"
_staged2.write_bytes(b"ISO-10303-21;\n/* MODEL C */\nEND-ISO-10303-21;\n")
_id_before = ash.ifc_identity(_p.source_ifc)
os.replace(_staged2, FINAL)
_db.refresh(_p)
check("...and the COLUMN does not move across that same publication, which is the whole reason it "
      "cannot be the check -- read back from the row after the replace, not asserted about a literal",
      _p.source_ifc == _col_before and ash.ifc_identity(_p.source_ifc) != _id_before,
      f"column {_col_before!r} unchanged; identity {_id_before} -> {ash.ifc_identity(_p.source_ifc)}")
_db.close()
check("an unreadable path is `None`, not a value that compares equal to another `None` by accident "
      "-- the callers treat either side being `None` as a MISMATCH, so a vanished file fails closed",
      ash.ifc_identity(WORK / "not-there.ifc") is None and ash.ifc_identity(None) is None)


# ---------------------------------------------------------------------------------------------
# B2. The route: a publication landing mid-takeoff.
# ---------------------------------------------------------------------------------------------
def sync_with_republish(*, guard: bool) -> int | None:
    """Run `sync_model_to_hard` with a publication landing DURING the takeoff.

    `guard=False` replaces the file identity with the path string -- which is precisely what a check
    written against `p.source_ifc` compares, and the reason that check is a no-op.
    """
    model = WORK / f"route-{'g' if guard else 'm'}.ifc"
    model.write_bytes(b"ISO-10303-21;\n/* MODEL A */\nEND-ISO-10303-21;\n")
    reset(budget=SOFT_ONLY)
    db = SessionLocal()
    p = db.get(Project, PID)
    p.source_ifc = str(model)
    db.commit()

    import aec_data.qto as _qto
    from aec_api import estimate as _est
    real_takeoff, real_estimate, real_identity = _qto.takeoff_file, _est.estimate_from_takeoff, ash.ifc_identity

    def republishing_takeoff(path, **_kw):
        """The publication lands here -- between the identity capture and the commit."""
        newer = WORK / f"newer-{'g' if guard else 'm'}.ifc"
        newer.write_bytes(b"ISO-10303-21;\n/* MODEL B -- published mid-takeoff */\nEND-ISO-10303-21;\n")
        os.replace(newer, path)                                # same path, new inode
        return []

    _qto.takeoff_file = republishing_takeoff
    _est.estimate_from_takeoff = lambda _rows, **_kw: {"lines": [], "recommended_total": 7_500_000.0}
    if not guard:
        ash.ifc_identity = str                                 # i.e. compare the PATH, as the column does
    try:
        pf.sync_model_to_hard(PID, db=db, _sec=ACTOR)
        return 200
    except BaseException as e:                                 # noqa: BLE001
        return status_of(e)
    finally:
        _qto.takeoff_file, _est.estimate_from_takeoff, ash.ifc_identity = (
            real_takeoff, real_estimate, real_identity)
        db.close()


check("THE SECOND DEFECT: a publication landing during the takeoff makes the sync a 409 rather than "
      "a committed hard cost derived from a model the project no longer has",
      sync_with_republish(guard=True) == 409)
check("MUTATION: comparing the PATH instead of the file identity -- what a check written against "
      "`p.source_ifc` does -- lets the same interleaving commit with a 200. *A staleness check "
      "against a field the writer does not move always passes.*",
      sync_with_republish(guard=False) == 200)


# ---------------------------------------------------------------------------------------------
# C. The one caller that races must keep sending `rev`.
#    `rev` being optional is a bounded decision, not a fail-open default -- and what bounds it is
#    this, not the sentence in the route saying so.
# ---------------------------------------------------------------------------------------------
_WEB = pathlib.Path(__file__).resolve().parent.parent.parent / "apps" / "web" / "src"
_api_src = (_WEB / "api" / "proforma.ts").read_text(encoding="utf-8")
_panel_src = (_WEB / "proforma" / "proforma.ts").read_text(encoding="utf-8")

check("the web API layer DECLARES `rev` on the save body -- without it the field is dropped at the "
      "type boundary and the server sees a request with no precondition",
      "rev?: string | null" in _api_src, "apps/web/src/api/proforma.ts")
check("the budget panel SENDS it, and re-reads the one the server hands back -- a panel that sent "
      "the rev it loaded once would 409 on its own second keystroke",
      "saveDevBudget(pid, { lines, contingency, rev })" in _panel_src
      and "rev = r.rev ?? null" in _panel_src, "apps/web/src/proforma/proforma.ts")
check("...and it HANDLES the 409 by reloading rather than retrying -- a retry carrying the fresh rev "
      "would re-send exactly the body the server refused, which is the defect with an extra step",
      "409" in _panel_src and "reloadAfterConflict" in _panel_src,
      "apps/web/src/proforma/proforma.ts")

print(f"\ntest_budget_rev {'FAILED' if FAILED else 'OK'}")
for f in FAILED:
    print(f"  - {f}")
#: Removed only on a PASS -- a failed run's staged and published models are the evidence somebody
#: will want, and a fixed directory would arm the next run with this one's leftovers.
if not FAILED:
    shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if FAILED else 0)
