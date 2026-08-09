"""A function that mutates a model and writes it must not have opened it through the shared cache.

THE RULE. `ifc_loader.open_model` returns a SHARED, MUTABLE model from a `(path, mtime, size)` cache.
Mutating one and writing it elsewhere leaves the cache entry for the INPUT path describing a file it
no longer matches, and the next reader of that version is silently handed a different model under its
name. `open_model_for_write` exists so the mutating case is spelled differently from the reading case.

WHY A GATE AND NOT FOUR FIXES. The four mutating readers were written by different people at
different times, and three had no idea the hazard existed:

    edit.apply_recipe / apply_recipes    the authoring loop
    nodegraph.execute_graph              /edit/graph, the visual node canvas
    routers/authoring import_types (x2)  manufacturer / family-pack type import

The fourth — `routers/bim.py`'s subset export — DID know, and defended itself locally with an
uncached `ifcopenshell.open` and a comment explaining why. That is the shape [[correct-twice-missed-once]]
warns about: one site correct proves nothing about the others, and a local workaround teaches
nothing to the next person. So the rule is enforced over the whole tree instead of remembered.

HOW IT IS DETECTED, AND WHAT IT CANNOT SEE. A function that calls `open_model(...)` and also calls
`.write(...)` on anything is flagged. That over-reports on purpose — `model_options.diff_option`
opens two models read-only and separately writes a tempfile, which is harmless — so genuinely-safe
functions are listed by name in `_ALLOWED` with a reason. Requiring an exemption entry is the point:
[[derive-the-population-and-the-reach]] — needing one is the signal that a human looked.

It CANNOT see a mutation that happens in a helper several frames away with the write in a third
function. This gate catches the shape that produced every known instance; it is not a proof.

Three other mutate-and-write sites need no exemption because they never touch this cache at all —
`routers/analysis.py`'s scan verification, `routers/bim.py`'s subset export, and `routers/design.py`'s
re-colour each open with a bare `ifcopenshell.open`. They are named here rather than listed as
exemptions on purpose: an allowlist entry for a function the detector never flags is a stale
exemption from birth, which the second test below refuses. That test caught exactly this mistake in
the first draft of this file.
"""
from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TREES = (_ROOT / "services" / "data" / "src" / "aec_data",
          _ROOT / "services" / "api" / "src" / "aec_api")

#: Functions where the pattern is a false positive. Name the reason, not just the function — an
#: exemption with no argument is a suppression.
_ALLOWED = {
    "model_options.py::diff_option":
        "opens two models READ-ONLY (by_type only) and the .write() is a tempfile write, not a model "
        "write",
}


def _offenders() -> dict[str, int]:
    """{'<file>::<func>': lineno} for every function that both opens via the cache and writes."""
    out: dict[str, int] = {}
    for tree_root in _TREES:
        for path in sorted(tree_root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            rel = path.relative_to(tree_root).as_posix()
            for fn in [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                opens = writes = False
                for node in ast.walk(fn):
                    if not isinstance(node, ast.Call):
                        continue
                    f = node.func
                    # `open_model(...)` exactly — NOT `open_model_for_write`, which is the fix.
                    if isinstance(f, ast.Name) and f.id == "open_model":
                        opens = True
                    if isinstance(f, ast.Attribute) and f.attr == "open_model":
                        opens = True
                    if isinstance(f, ast.Attribute) and f.attr == "write":
                        writes = True
                if opens and writes:
                    out[f"{rel}::{fn.name}"] = fn.lineno
    return out


def test_no_mutating_reader_uses_the_cached_opener() -> None:
    found = _offenders()
    unexpected = {k: v for k, v in found.items() if k not in _ALLOWED}
    assert not unexpected, (
        "these functions call open_model() and also write — if the model they write is the one they "
        "opened, the cache will serve the NEXT version under the OLD version's name:\n"
        + "\n".join(f"  {k}  (line {v})" for k, v in sorted(unexpected.items()))
        + "\nUse ifc_loader.open_model_for_write, or add an entry to _ALLOWED WITH THE REASON if the "
          "write is unrelated to the opened model."
    )
    print(f"PASS  no mutating reader opens through the cache   "
          f"{len(found)} matched the shape, all {len(found)} accounted for")


def test_the_allowlist_does_not_name_functions_that_no_longer_exist() -> None:
    """A stale exemption is a hole nobody can see.

    If a function is renamed or deleted and its entry stays, the entry silently begins exempting
    nothing — and would go on 'passing' if a NEW function later took that name for a real violation.
    An allowlist that is never checked against reality is the failure mode allowlists have.
    """
    found = _offenders()
    stale = sorted(set(_ALLOWED) - set(found))
    assert not stale, (
        f"_ALLOWED names functions that no longer match the pattern: {stale}. Remove them — a stale "
        f"exemption exempts nothing today and something unknown tomorrow.")
    print(f"PASS  every exemption still corresponds to a real function   {len(_ALLOWED)} exemptions")


def test_the_scan_actually_finds_something() -> None:
    """Vacuity check. If the AST walk silently stopped matching, both tests above would pass while
    measuring an empty set — which is the exact shape of a gate that cannot fail."""
    found = _offenders()
    assert found, ("the scan matched NO functions at all. Either every mutating reader was removed "
                   "(check before believing it) or this detector is broken and proving nothing.")
    print(f"PASS  the scan is not vacuous   {len(found)} function(s) match the open+write shape")


if __name__ == "__main__":
    test_no_mutating_reader_uses_the_cached_opener()
    test_the_allowlist_does_not_name_functions_that_no_longer_exist()
    test_the_scan_actually_finds_something()
    print("test_mutating_readers OK")
