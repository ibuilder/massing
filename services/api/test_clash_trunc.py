"""CLASH-TRUNC — the coordination matrix is entitled to claim only what the run actually covered.

``soft_clash.matrix`` exists to refuse one sentence: *"clash-free"* over a partial matrix. Its third
state — ``untested``, never folded into ``clean`` — is the whole design, and the module's docstring
says so. **It was defeated from outside.**

``/clash/federated`` (and the ``clash_federated`` job kind the coordination screen actually runs)
returns ``count`` for the whole run and ``clashes`` for the first ``limit`` of them, with a
``truncated`` flag nobody read. The panel built the matrix's ``findings`` out of that PAGE while
declaring EVERY discipline pair tested. So a pair whose clashes all sit past the limit arrived with
no evidence and landed in ``clean`` rather than ``untested``.

**The severity is bounded, and the first draft of this docstring got it wrong in the flattering
direction** — it said ``coordinated`` could come back true over thousands of clashes. Measured
rather than asserted: it cannot, on this path. ``coordinated`` demands zero ``clashes`` cells, and a
truncated page always carries at least one finding, so it is false whenever the defect fires. What
the defect DOES produce is measured below: ``coverage_pct: 100.0`` and ``untested: 0`` — the matrix
stating that every pair was examined — beside a ``clean`` cell for a pair with 918 clashes in it.
*A wrong cell that a coordination meeting acts on is quite bad enough; claiming the headline flag
too would have made this file evidence for something it cannot reproduce.*

*The engine refused the claim it was built to refuse; its caller supplied a premise that made the
refusal moot for five of six cells.* A guard is only as sound as the evidence it is handed, and
nothing here was checking the evidence.

Two halves, and **either alone still ships the defect**:

* ``soft_clash.pair_tally`` counts per pair over the WHOLE result list, computed where the full list
  still exists — in both federated paths, beside the page they truncate.
* ``soft_clash.finding_weight`` lets one finding entry stand for many clashes, so the tally can
  travel in the shape ``matrix`` already takes.

Run from ``services/api``:
    PYTHONPATH="src:../data/src" .venv/bin/python test_clash_trunc.py
"""
import ast
import os
import pathlib

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_clash_trunc.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_clash_trunc")

from aec_api import soft_clash as sc  # noqa: E402

SRC = pathlib.Path(__file__).resolve().parent / "src" / "aec_api"
DISCS = ["ARC", "MEP", "STR"]
LIMIT = 200

#: A run whose clashes are NOT evenly spread: every one of the first `LIMIT` is STR×MEP, and the
#: 918 ARC×MEP hits are entirely past the page. That skew is the defect's precondition, so it is
#: asserted below rather than assumed — a fixture whose page happens to name every pair would make
#: this whole file pass against the pre-fix code.
RESULTS = ([{"a_model": "STR", "b_model": "MEP", "a_class": "IfcBeam", "b_class": "IfcDuctSegment"}
            for _ in range(520)]
           + [{"a_model": "ARC", "b_model": "MEP", "a_class": "IfcWall", "b_class": "IfcPipeSegment"}
              for _ in range(918)])
PAGE = RESULTS[:LIMIT]
EVERY_PAIR = [(a, b) for i, a in enumerate(DISCS) for b in DISCS[i:]]


def _pair_names(rows):
    return {sc.pair_key(r["a_model"], r["b_model"]) for r in rows}


def _cell(m, a, b):
    k = sc.pair_key(a, b)
    return next(c for c in m["cells"] if (c["a"], c["b"]) == k)


# ---- the precondition, asserted before anything is concluded from it ----------------------------
assert len(RESULTS) > LIMIT, "the fixture is not truncated and cannot exercise this"
assert _pair_names(PAGE) == {("MEP", "STR")}, \
    (f"the page must name FEWER pairs than the run — a fixture whose first {LIMIT} clashes already "
     "cover every pair passes against the pre-fix code too")
assert ("ARC", "MEP") in _pair_names(RESULTS)

# ---- THE DEFECT, reinstated: a matrix built from the PAGE calls an unexamined pair clean ---------
as_findings = [{"discipline_a": r["a_model"], "discipline_b": r["b_model"]} for r in PAGE]
pre_fix = sc.matrix(DISCS, EVERY_PAIR, as_findings)
assert _cell(pre_fix, "ARC", "MEP")["state"] == "clean", \
    "the pre-fix shape no longer reproduces — re-derive before trusting anything below"
assert _cell(pre_fix, "ARC", "ARC")["state"] == "clean"
assert pre_fix["counts"]["clean"] == 5 and pre_fix["counts"]["clashes"] == 1

# THE BOUND, measured rather than claimed. `coordinated` is NOT reachable here: it demands zero
# `clashes` cells and a truncated page always carries a finding. What IS reachable is the matrix
# asserting it examined everything — full coverage, nothing untested — with five of six cells wrong.
assert pre_fix["coordinated"] is False, \
    "if this ever becomes true the bound in the docstring is wrong and must be rewritten, not muted"
assert pre_fix["coverage_pct"] == 100.0 and pre_fix["counts"]["untested"] == 0, \
    "the damage is the CLAIM of full coverage sitting on top of unexamined pairs"

# ---- THE FIX: the tally is over the whole run, so the pair is `clashes` and nothing is clean-washed
tally = sc.pair_tally(RESULTS)
assert tally == [{"discipline_a": "ARC", "discipline_b": "MEP", "count": 918},
                 {"discipline_a": "MEP", "discipline_b": "STR", "count": 520}], tally
fixed = sc.matrix(DISCS, EVERY_PAIR, tally)
assert _cell(fixed, "ARC", "MEP")["state"] == "clashes"
assert _cell(fixed, "ARC", "MEP")["count"] == 918, \
    "the cell must carry the RUN's count — a weight of 1 understates the pair by 917"
assert fixed["coordinated"] is False
assert fixed["counts"]["clashes"] == 2 and fixed["counts"]["clean"] == 4

# a tally taken from the PAGE is exactly the defect wearing the fix's clothes
assert _cell(sc.matrix(DISCS, EVERY_PAIR, sc.pair_tally(PAGE)), "ARC", "MEP")["state"] == "clean"

# ---- the weight, and the direction its failure must fall in --------------------------------------
assert sc.finding_weight({"count": 7}) == 7
# A malformed count weighs ONE, never zero: the entry's existence is evidence the pair clashes, so a
# corrupt number must not be able to delete a finding that a MISSING number would have kept.
for bad in ({}, {"count": None}, {"count": "9"}, {"count": 0}, {"count": -3}, {"count": True},
            {"count": 2.5}):
    assert sc.finding_weight(bad) == 1, bad
assert _cell(sc.matrix(DISCS, EVERY_PAIR,
                       [{"discipline_a": "ARC", "discipline_b": "MEP", "count": "lots"}]),
             "ARC", "MEP")["state"] == "clashes", \
    "a finding with an unreadable count must still mark its pair as clashing"

# a bare findings list — one entry per clash, no counts — is unchanged by the weight
assert sc.matrix(DISCS, EVERY_PAIR, as_findings)["counts"] == pre_fix["counts"]

# ---- degenerate tallies must not fabricate anything ----------------------------------------------
assert sc.pair_tally([]) == [] and sc.pair_tally(None) == []
# a result with no model name falls back to its IFC class rather than vanishing into a "?" bucket
assert sc.pair_tally([{"a_class": "IfcBeam", "b_class": "IfcDuctSegment"}]) == \
    [{"discipline_a": "IfcBeam", "discipline_b": "IfcDuctSegment", "count": 1}]
assert sc.pair_tally([{}]) == [{"discipline_a": "?", "discipline_b": "?", "count": 1}]
# order-independence: MEP×STR and STR×MEP are one pair, as `pair_key` promises
assert sc.pair_tally([{"a_model": "STR", "b_model": "MEP"}, {"a_model": "MEP", "b_model": "STR"}]) \
    == [{"discipline_a": "MEP", "discipline_b": "STR", "count": 2}]

# ---- BOTH federated paths must tally the FULL list, and that is a structural claim ---------------
# The job kind is what the coordination screen runs; the route is what the API client method calls.
# Neither can be driven from here without two IFC files and the geometry engine, so this reads their
# source: the `pair_counts` value must be `pair_tally(results)` with `results` as a bare name. A
# subscript there — `results[:limit]` — IS the defect, and is what the self-check below mutates in.
def _returns_full_tally(path: pathlib.Path, func: str) -> tuple[bool, str]:
    """(ok, why). Derived from the AST of the function's `return`, never from a substring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func), None)
    if fn is None:
        return False, f"{func} not found in {path.name}"
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if not (isinstance(k, ast.Constant) and k.value == "pair_counts"):
                continue
            if not (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                    and v.func.attr == "pair_tally"):
                return False, f"{func}: pair_counts is not a pair_tally() call"
            arg = v.args[0] if v.args else None
            # The binding must be `results`, not merely SOME name. Raised in review: a bare-Name
            # check passes `pair_tally(page)` where `page = results[:limit]` — the defect restored
            # through a variable instead of inline, which is the shape a later refactor produces.
            # *An analyser that accepts any name has stopped reading the argument and started
            # reading its syntax class.*
            if isinstance(arg, ast.Name) and arg.id == "results":
                return True, f"{func}: pair_tally({arg.id})"
            if isinstance(arg, ast.Name):
                return False, (f"{func}: pair_tally({arg.id}) — the tally must be taken over the "
                               f"full `results` binding, and any other name may already be a page")
            return False, (f"{func}: pair_tally() is given "
                           f"{type(arg).__name__} — a slice here IS the defect")
        return False, f"{func}: the returned dict carries no pair_counts"
    return False, f"{func}: no dict return found"


PATHS = {("jobs.py", "_clash_federated"): SRC / "jobs.py",
         ("analysis.py", "run_clash_federated"): SRC / "routers" / "analysis.py"}
for (_, func), path in PATHS.items():
    ok, why = _returns_full_tally(path, func)
    assert ok, why

# The analyser must be able to FAIL — a structural check that cannot is the thing this repository
# keeps paying for. Both known-wrong shapes are run through it rather than described.
_mutants = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "_clash_trunc_mutants"
_mutants.mkdir(parents=True, exist_ok=True)
_src = (SRC / "jobs.py").read_text(encoding="utf-8")
for name, wrong, expect in (
        ("page", "soft_clash.pair_tally(results[:limit])", "a slice here IS the defect"),
        # The review's shape: the slice moved behind a name. A bare-Name check calls this correct.
        ("alias", "soft_clash.pair_tally(page)", "must be taken over the full `results` binding"),
        ("gone", "None", "not a pair_tally() call")):
    f = _mutants / f"jobs_{name}.py"
    f.write_text(_src.replace("soft_clash.pair_tally(results)", wrong, 1), encoding="utf-8")
    ok, why = _returns_full_tally(f, "_clash_federated")
    assert not ok and expect in why, (name, ok, why)
    f.unlink()
_mutants.rmdir()

print("CLASH-TRUNC OK - a coordination matrix may claim only what the run covered, and the guard "
      "that enforces that was defeated from OUTSIDE rather than broken. `soft_clash.matrix` refuses "
      "one sentence - 'clash-free' over a partial matrix - by keeping `untested` separate from "
      "`clean`; the federated clash screen built its findings from the PAGE the server returns "
      "while declaring every discipline pair tested, so a pair whose clashes all sat past the limit "
      "arrived with no evidence and was reported CLEAN. Measured on the fixture here: 1,438 clashes "
      "of which 918 are ARC x MEP, none of them on the first 200, and the pre-fix shape reports "
      "that pair clean at `coverage_pct: 100` with nothing untested - the matrix asserting it "
      "examined everything, on top of five cells it never saw. The headline `coordinated` flag is "
      "NOT reachable this way and the first draft of this file said it was: that flag needs zero "
      "clashing cells and a truncated page always carries a finding. A bound checked is worth more "
      "than a severity asserted. The repair is a per-pair tally computed where the WHOLE list "
      "still exists, in both federated paths, travelling beside the page rather than replacing it: "
      "the list is what a person clicks, the tally is what a report may claim. A malformed count "
      "weighs one and never zero, because the entry's existence is itself evidence the pair "
      "clashes, and a corrupt number must not be quieter than a missing one.")
